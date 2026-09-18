import os
import time

import docker
import requests
from docker.errors import DockerException, ImageNotFound
from docker.models.containers import Container

from .models import DistroStatus, RunReport, SingleResult


def run_script_on_distros(script_path: str, distros: list[str], timeout: int = 60) -> RunReport:
    """Runs a shell script on multiple distros."""
    report = RunReport(script_path=script_path)

    try:
        client = docker.from_env()
    except DockerException as e:
        for distro in distros:
            report.results.append(
                SingleResult(
                    image=distro,
                    status=DistroStatus.ERROR,
                    exit_code=None,
                    stdout="",
                    stderr=f"Docker connection failed: {e}",
                    execution_time=0.0,
                )
            )
        return report

    abs_script_path = os.path.abspath(script_path)

    for distro in distros:
        result = _run_on_single_distro(client, abs_script_path, distro, timeout)
        report.results.append(result)

    return report

def _run_on_single_distro(client: docker.DockerClient, script_path: str, image: str, timeout: int) -> SingleResult:
    start_time = time.time()

    try:
        try:
            client.images.get(image)
        except ImageNotFound:
            client.images.pull(image)
    except DockerException as e:
        return SingleResult(
            image=image,
            status=DistroStatus.ERROR,
            exit_code=None,
            stdout="",
            stderr=f"Failed to pull image {image}: {e}",
            execution_time=time.time() - start_time,
        )

    container: Container | None = None
    try:
        container = client.containers.run(
            image=image,
            command=["sh", "-c", "/opt/script.sh"],
            volumes={script_path: {"bind": "/opt/script.sh", "mode": "ro"}},
            environment={"DEBIAN_FRONTEND": "noninteractive"},
            detach=True,
            stdin_open=False, # Disconnect stdin to prevent interactive hangs
            privileged=False,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
        )

        try:
            wait_res = container.wait(timeout=timeout)
            exit_code = wait_res.get("StatusCode", -1)
            status = DistroStatus.PASS if exit_code == 0 else DistroStatus.FAIL
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            # Timeout happened! Kill the container.
            container.kill()
            exit_code = None
            status = DistroStatus.TIMEOUT

        stdout_logs = container.logs(stdout=True, stderr=False, stream=False).decode("utf-8", errors="replace")
        stderr_logs = container.logs(stdout=False, stderr=True, stream=False).decode("utf-8", errors="replace")

        return SingleResult(
            image=image,
            status=status,
            exit_code=exit_code,
            stdout=stdout_logs,
            stderr=stderr_logs,
            execution_time=time.time() - start_time,
        )

    except Exception as e:
        return SingleResult(
            image=image,
            status=DistroStatus.ERROR,
            exit_code=None,
            stdout="",
            stderr=str(e),
            execution_time=time.time() - start_time,
        )
    finally:
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass
