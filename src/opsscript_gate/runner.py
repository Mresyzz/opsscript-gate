from __future__ import annotations

import os
import tempfile
import time
from typing import Sequence

import docker
from docker.errors import DockerException, ImageNotFound

from opsscript_gate.models import DistroStatus, RunReport, SingleResult

DEFAULT_MATRIX: list[str] = [
    "debian:12-slim",
    "ubuntu:22.04",
    "ubuntu:24.04",
    "alpine:3.20",
]

DEFAULT_TIMEOUT: int = 60
SNIPPET_LINE_LIMIT: int = 15


class DockerDaemonError(RuntimeError):
    """Raised when the Docker daemon is unreachable or not running."""
    pass


def get_docker_client() -> docker.DockerClient:
    """Connect to the Docker daemon with clear human-readable error handling."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as exc:
        raise DockerDaemonError(
            f"Cannot connect to Docker daemon: {exc}. "
            "Please ensure Docker is installed, running, and accessible."
        ) from exc
    except Exception as exc:
        raise DockerDaemonError(
            f"Unexpected error connecting to Docker daemon: {exc}."
        ) from exc


def extract_snippet(output: str, max_lines: int = SNIPPET_LINE_LIMIT) -> str:
    """Extract the last max_lines of output."""
    if not output:
        return ""
    lines = output.strip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def normalize_host_path_for_docker(path: str) -> str:
    """Format path to be safe for Docker volume mounting on both Windows and POSIX."""
    abs_path = os.path.abspath(path)
    # On Windows, Docker client handles forward slashes cleanly without colon misparsing
    return abs_path.replace("\\", "/")


def prepare_script(script_path: str) -> tuple[str, tempfile.NamedTemporaryFile | None]:
    """
    Check and normalize line endings (CRLF -> LF) to defend against
    '\\r: command not found' errors in Linux containers (especially Alpine).
    Returns (path_to_mount, temp_file_or_none).
    """
    abs_path = os.path.abspath(script_path)
    with open(abs_path, "rb") as f:
        content = f.read()

    if b"\r\n" in content:
        # Normalize CRLF to LF in a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".sh")
        temp_file.write(content.replace(b"\r\n", b"\n"))
        temp_file.flush()
        temp_file.close()
        return temp_file.name, temp_file

    return abs_path, None


def run_on_distro(
    client: docker.DockerClient,
    script_path: str,
    distro: str,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: float = 0.1,
) -> SingleResult:
    """
    Run a target script inside an unprivileged, non-interactive container.
    Strictly uses /bin/sh for 100% compatibility with Alpine, Debian, and Ubuntu.
    """
    abs_script = os.path.abspath(script_path)
    if not os.path.isfile(abs_script):
        return SingleResult(
            distro=distro,
            status=DistroStatus.ERROR,
            exit_code=None,
            duration=0.0,
            output_snippet="",
            error_message=f"Target script does not exist: {abs_script}",
        )

    # Line-ending defense & Windows-safe path preparation
    temp_file = None
    try:
        mount_src, temp_file = prepare_script(abs_script)
    except Exception as exc:
        return SingleResult(
            distro=distro,
            status=DistroStatus.ERROR,
            exit_code=None,
            duration=0.0,
            output_snippet="",
            error_message=f"Failed to read/prepare script: {exc}",
        )

    safe_mount_src = normalize_host_path_for_docker(mount_src)

    # Security: Strict unprivileged options and read-only mount
    volumes = {
        safe_mount_src: {
            "bind": "/tmp/target_script.sh",
            "mode": "ro",
        }
    }
    environment = {
        "DEBIAN_FRONTEND": "noninteractive",
        "CI": "true",
    }
    # Red-line rule: strictly /bin/sh (never hardcode /bin/bash for Alpine compatibility)
    # Redirect stdin from /dev/null to defend against interactive hangs
    command = ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"]

    container = None
    start_time = time.perf_counter()

    try:
        try:
            container = client.containers.create(
                image=distro,
                command=command,
                volumes=volumes,
                environment=environment,
                stdin_open=False,
                tty=False,
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                network_mode="bridge",
                detach=True,
            )
        except ImageNotFound:
            client.images.pull(distro)
            container = client.containers.create(
                image=distro,
                command=command,
                volumes=volumes,
                environment=environment,
                stdin_open=False,
                tty=False,
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                network_mode="bridge",
                detach=True,
            )

        container.start()

        # Hard timeout monitoring with container.kill()
        timed_out = False
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= timeout:
                timed_out = True
                try:
                    container.kill()
                except Exception:
                    pass
                break

            container.reload()
            status_str = container.status.lower()
            if status_str in ("exited", "dead", "stopped"):
                break

            time.sleep(poll_interval)

        duration = time.perf_counter() - start_time

        # Retrieve container logs
        try:
            raw_logs = container.logs(stdout=True, stderr=True)
            output = raw_logs.decode("utf-8", errors="replace") if isinstance(raw_logs, bytes) else str(raw_logs)
        except Exception:
            output = ""

        if timed_out:
            return SingleResult(
                distro=distro,
                status=DistroStatus.TIMED_OUT,
                exit_code=None,
                duration=duration,
                output_snippet=extract_snippet(output),
                error_message=f"Execution timed out after {timeout} seconds (container killed)",
            )

        container.reload()
        state = getattr(container, "attrs", {}).get("State", {})
        exit_code = state.get("ExitCode")

        if exit_code is None:
            exit_code = 0 if container.status == "exited" else 1

        if exit_code == 0:
            return SingleResult(
                distro=distro,
                status=DistroStatus.PASS,
                exit_code=0,
                duration=duration,
                output_snippet=extract_snippet(output) if output.strip() else "",
                error_message=None,
            )
        else:
            return SingleResult(
                distro=distro,
                status=DistroStatus.FAIL,
                exit_code=exit_code,
                duration=duration,
                output_snippet=extract_snippet(output),
                error_message=f"Script failed with non-zero exit code: {exit_code}",
            )

    except Exception as exc:
        duration = time.perf_counter() - start_time
        return SingleResult(
            distro=distro,
            status=DistroStatus.ERROR,
            exit_code=None,
            duration=duration,
            output_snippet="",
            error_message=f"Container execution error: {exc}",
        )
    finally:
        # Zero-zombie guarantee: always remove container
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        # Clean up temporary CRLF normalized file if created
        if temp_file is not None:
            try:
                if os.path.exists(temp_file.name):
                    os.remove(temp_file.name)
            except Exception:
                pass


def run_matrix(
    script_path: str,
    matrix: Sequence[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    client: docker.DockerClient | None = None,
) -> RunReport:
    """Run the compatibility check across all specified Linux distributions."""
    distro_list = list(matrix) if matrix else DEFAULT_MATRIX
    docker_client = client or get_docker_client()

    start_total = time.perf_counter()
    results: list[SingleResult] = []

    for distro in distro_list:
        res = run_on_distro(
            client=docker_client,
            script_path=script_path,
            distro=distro,
            timeout=timeout,
        )
        results.append(res)

    total_duration = time.perf_counter() - start_total
    all_passed = all(r.status == DistroStatus.PASS for r in results) if results else True

    return RunReport(
        results=results,
        total_duration=total_duration,
        all_passed=all_passed,
    )
