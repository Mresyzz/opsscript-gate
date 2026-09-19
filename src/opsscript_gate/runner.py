from __future__ import annotations

import os
import re
import tempfile
import time
from typing import Sequence

import docker
from docker.errors import DockerException, ImageNotFound

from dataclasses import dataclass
from enum import Enum
from opsscript_gate.models import DistroStatus, FailureDiagnostic, RunReport, ShellMode, SingleResult

DEFAULT_MATRIX: list[str] = [
    "debian:12-slim",
    "ubuntu:22.04",
    "ubuntu:24.04",
    "alpine:3.20",
]

DEFAULT_TIMEOUT: int = 60
SNIPPET_LINE_LIMIT: int = 15

# Fixed trusted command mappings for supported shebang interpreter forms.
# Any executed command is guaranteed to come strictly from this predefined constant map.
SUPPORTED_SHEBANG_COMMANDS: dict[str, list[str]] = {
    "/bin/sh": ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"],
    "/usr/bin/sh": ["/bin/sh", "-c", "/usr/bin/sh /tmp/target_script.sh </dev/null"],
    "/bin/bash": ["/bin/sh", "-c", "/bin/bash /tmp/target_script.sh </dev/null"],
    "/usr/bin/bash": ["/bin/sh", "-c", "/usr/bin/bash /tmp/target_script.sh </dev/null"],
    "/usr/bin/env sh": ["/bin/sh", "-c", "/usr/bin/env sh /tmp/target_script.sh </dev/null"],
    "/usr/bin/env bash": ["/bin/sh", "-c", "/usr/bin/env bash /tmp/target_script.sh </dev/null"],
}

DEFAULT_POSIX_COMMAND: list[str] = ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"]

# Regular expression matching common ANSI escape sequences:
# 1. CSI (Control Sequence Introducer): ESC [ ... [@-~]
# 2. OSC (Operating System Command): ESC ] ... (BEL | ST)
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))"
)


def sanitize_diagnostic_text(text: str, max_length: int = 200) -> str:
    """
    Sanitize raw shebang text for safe display in diagnostics and error messages:
    - Strips complete ANSI escape sequences (CSI, OSC)
    - Removes control characters and embedded CR/LF
    - Collapses multiple consecutive whitespace
    - Ensures maximum final length <= max_length (including ellipsis if truncated)
    """
    if not text or max_length <= 0:
        return ""
    # Strip complete ANSI escape sequences first
    text = _ANSI_ESCAPE_RE.sub("", text)
    # Filter out control characters (ASCII < 32 and 127)
    sanitized = "".join(ch if (32 <= ord(ch) < 127 or ord(ch) >= 160) else " " for ch in text)
    # Collapse multiple consecutive whitespace
    sanitized = " ".join(sanitized.split())
    if len(sanitized) > max_length:
        if max_length < 3:
            return sanitized[:max_length]
        return sanitized[: max_length - 3] + "..."
    return sanitized


# Conservative regular expression matching recognized shell-origin 'not found' error patterns:
# Examples:
#   - BusyBox ash: "sh: line 4: apt-get: not found", "sh: curl: not found", "/bin/sh: ...: not found"
#   - Debian dash: "dash: 1: curl: not found", "sh: 1: curl: not found"
#   - Bash: "bash: line 4: foo: command not found", "bash: foo: command not found"
#   - /bin/sh: "/bin/sh: line 1: /usr/bin/bash: not found", "/bin/sh: curl: not found"
#   - script-path + line-number forms: "/tmp/target_script.sh: line 4: curl: not found", "test.sh: 4: curl: not found"
_MISSING_COMMAND_RE = re.compile(
    r"""
    (?:^|(?<=[\r\n]))                                  # start of line
    \s*
    (?:
        (?:/(?:usr/)?bin/)?(?:sh|bash|dash|ash)        # recognized shell interpreter name
        (?::\s*[^:\r\n]+)?                             # optional script path within shell error
        (?::\s*(?:line\s+\d+|\d+))?                    # optional line indicator
        |
        [^:\r\n]+?:\s*(?:line\s+\d+|\d+)               # script-path + line-number forms
    )
    :\s+                                               # separator after shell-origin prefix
    (?P<cmd>['"`]?[\w./+-]+['"`]?)                     # strictly valid command identifier/path
    :\s+                                               # colon separator
    (?:command\s+not\s+found|not\s+found)              # missing command indicator
    \s*(?=$|[\r\n])                                    # end of line
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

# Strict whitelist for extracted command token validation (alphanumerics, Unicode words, dots, dashes, slashes):
_VALID_COMMAND_TOKEN_RE = re.compile(r"^[\w./+-]+$")

# Common status, protocol, and message prefixes that must never be classified as missing commands:
_NON_COMMAND_TOKENS = {
    "status", "error", "warning", "info", "notice", "message",
    "file", "directory", "entry", "key", "value", "user", "record",
    "http", "https", "response", "request", "server", "client",
}


def extract_failure_diagnostic(
    output: str,
    exit_code: int | None = None,
) -> FailureDiagnostic | None:
    """
    Extract high-confidence structured diagnostic from container execution failure.

    Deliberately conservative (prefer false negatives over false positives):
    - Requires exit_code == 127 as an essential high-confidence signal.
    - Requires matching a well-known shell 'not found' pattern in output.
    - Strictly validates command token syntax (no arbitrary text or markdown injection).
    - Excludes numeric status codes, status/error message prefixes, path-only dots/slashes, and unclassified output.
    - Returns None if not confidently classified as missing_command.
    """
    if exit_code != 127 or not output:
        return None

    # Strip ANSI escape sequences first
    cleaned_output = _ANSI_ESCAPE_RE.sub("", output)

    for line in cleaned_output.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        m = _MISSING_COMMAND_RE.search(line_clean)
        if not m:
            continue

        raw_cmd = m.group("cmd").strip("'\"`")
        if not raw_cmd or raw_cmd.isdigit():
            continue

        # Disallow pure dot/slash sequences
        if raw_cmd in (".", "..", "/", "//"):
            continue

        # Exclude common non-command tokens and protocol prefixes (e.g. Status, Error, HTTP/1.1)
        lowered = raw_cmd.lower()
        if lowered in _NON_COMMAND_TOKENS or lowered.split("/")[0] in _NON_COMMAND_TOKENS:
            continue

        # Validate against strict conservative grammar
        if not _VALID_COMMAND_TOKEN_RE.match(raw_cmd):
            continue

        sanitized_cmd = sanitize_diagnostic_text(raw_cmd, max_length=100)
        if not sanitized_cmd or not _VALID_COMMAND_TOKEN_RE.match(sanitized_cmd):
            continue

        return FailureDiagnostic(
            kind="missing_command",
            command=sanitized_cmd,
            message=f"command not found: {sanitized_cmd}",
        )

    return None


class ShebangStatus(str, Enum):
    """Status of shebang parsing."""
    RECOGNIZED = "recognized"
    MISSING = "missing"
    MALFORMED = "malformed"
    UNSUPPORTED = "unsupported"


@dataclass
class ShebangParseResult:
    """Structured parse result for script shebang."""
    status: ShebangStatus
    command_key: str | None = None  # Key into SUPPORTED_SHEBANG_COMMANDS (e.g. "/bin/bash")
    interpreter: str | None = None  # "sh" | "bash" | None
    raw_shebang: str | None = None
    error_message: str | None = None


def inspect_shebang(script_path: str) -> ShebangParseResult:
    """
    Inspect the first line of a script to parse its shebang.
    Strict parsing rules:
      - Must begin with '#!' at index 0 (no leading whitespace allowed).
      - CRLF is normalized.
      - Supported forms: #!/bin/sh, #!/bin/bash, #!/usr/bin/sh,
        #!/usr/bin/bash, #!/usr/bin/env sh, #!/usr/bin/env bash.
      - Any shebang with additional arguments or complex env flags is rejected.
    """
    try:
        with open(script_path, "rb") as f:
            first_line_bytes = f.readline()
    except Exception as exc:
        return ShebangParseResult(
            status=ShebangStatus.MALFORMED,
            error_message=f"Failed to read script to parse shebang: {exc}",
        )

    # Normalize carriage returns and decode without lstripping leading characters
    raw_line = first_line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")

    # A valid shebang must begin at the very start of the first line
    if not raw_line.startswith("#!"):
        return ShebangParseResult(
            status=ShebangStatus.MISSING,
            error_message="No shebang found in script (required by --shell shebang)",
        )

    raw_shebang = raw_line
    shebang_body = raw_line[2:].strip()
    if not shebang_body:
        clean_shebang = sanitize_diagnostic_text(raw_shebang)
        return ShebangParseResult(
            status=ShebangStatus.MALFORMED,
            raw_shebang=raw_shebang,
            error_message=f"Malformed shebang in script: '{clean_shebang}'",
        )

    tokens = shebang_body.split()
    if not tokens:
        clean_shebang = sanitize_diagnostic_text(raw_shebang)
        return ShebangParseResult(
            status=ShebangStatus.MALFORMED,
            raw_shebang=raw_shebang,
            error_message=f"Malformed shebang in script: '{clean_shebang}'",
        )

    cmd = tokens[0]
    clean_shebang = sanitize_diagnostic_text(raw_shebang)

    # Handle /usr/bin/env
    if cmd == "/usr/bin/env":
        if len(tokens) == 1:
            return ShebangParseResult(
                status=ShebangStatus.MALFORMED,
                raw_shebang=raw_shebang,
                error_message=f"Malformed shebang in script: '{clean_shebang}' (missing interpreter)",
            )
        elif len(tokens) == 2:
            sub_cmd = tokens[1]
            if sub_cmd == "sh":
                return ShebangParseResult(
                    status=ShebangStatus.RECOGNIZED,
                    command_key="/usr/bin/env sh",
                    interpreter="sh",
                    raw_shebang=raw_shebang,
                )
            elif sub_cmd == "bash":
                return ShebangParseResult(
                    status=ShebangStatus.RECOGNIZED,
                    command_key="/usr/bin/env bash",
                    interpreter="bash",
                    raw_shebang=raw_shebang,
                )
            else:
                return ShebangParseResult(
                    status=ShebangStatus.UNSUPPORTED,
                    raw_shebang=raw_shebang,
                    error_message=f"Unsupported shebang interpreter: '{clean_shebang}' (supported: sh, bash)",
                )
        else:
            # Reject complex env forms (e.g. env -S bash) or additional arguments
            return ShebangParseResult(
                status=ShebangStatus.UNSUPPORTED,
                raw_shebang=raw_shebang,
                error_message=f"Unsupported complex env shebang form: '{clean_shebang}'",
            )

    # Direct interpreters (e.g. /bin/sh, /bin/bash, /usr/bin/sh, /usr/bin/bash)
    if cmd in ("/bin/sh", "/usr/bin/sh"):
        if len(tokens) > 1:
            return ShebangParseResult(
                status=ShebangStatus.UNSUPPORTED,
                raw_shebang=raw_shebang,
                error_message=f"Unsupported shebang arguments in '{clean_shebang}'",
            )
        return ShebangParseResult(
            status=ShebangStatus.RECOGNIZED,
            command_key=cmd,
            interpreter="sh",
            raw_shebang=raw_shebang,
        )
    elif cmd in ("/bin/bash", "/usr/bin/bash"):
        if len(tokens) > 1:
            return ShebangParseResult(
                status=ShebangStatus.UNSUPPORTED,
                raw_shebang=raw_shebang,
                error_message=f"Unsupported shebang arguments in '{clean_shebang}'",
            )
        return ShebangParseResult(
            status=ShebangStatus.RECOGNIZED,
            command_key=cmd,
            interpreter="bash",
            raw_shebang=raw_shebang,
        )
    else:
        return ShebangParseResult(
            status=ShebangStatus.UNSUPPORTED,
            raw_shebang=raw_shebang,
            error_message=f"Unsupported shebang interpreter: '{clean_shebang}' (supported: sh, bash)",
        )


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
    shell_mode: ShellMode | str = ShellMode.POSIX,
    parsed_shebang: ShebangParseResult | None = None,
) -> SingleResult:
    """
    Run a target script inside an unprivileged, non-interactive container.
    Supports posix, shebang, and auto execution modes.
    """
    try:
        mode = ShellMode(shell_mode)
    except ValueError:
        return SingleResult(
            distro=distro,
            status=DistroStatus.ERROR,
            exit_code=None,
            duration=0.0,
            output_snippet="",
            error_message=f"Invalid shell mode: '{shell_mode}'. Choose from: posix, shebang, auto.",
        )

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

    if mode == ShellMode.POSIX:
        # posix: strictly /bin/sh; do not parse shebang at all
        command = list(DEFAULT_POSIX_COMMAND)
    elif mode == ShellMode.SHEBANG:
        shebang_res = parsed_shebang if parsed_shebang is not None else inspect_shebang(abs_script)
        if shebang_res.status == ShebangStatus.MISSING:
            return SingleResult(
                distro=distro,
                status=DistroStatus.ERROR,
                exit_code=None,
                duration=0.0,
                output_snippet="",
                error_message="No shebang found in script (required by --shell shebang)",
            )
        if shebang_res.status == ShebangStatus.MALFORMED:
            return SingleResult(
                distro=distro,
                status=DistroStatus.ERROR,
                exit_code=None,
                duration=0.0,
                output_snippet="",
                error_message=shebang_res.error_message or "Malformed shebang in script",
            )
        if shebang_res.status == ShebangStatus.UNSUPPORTED:
            return SingleResult(
                distro=distro,
                status=DistroStatus.ERROR,
                exit_code=None,
                duration=0.0,
                output_snippet="",
                error_message=shebang_res.error_message or "Unsupported shebang interpreter",
            )
        cmd_key = shebang_res.command_key
        if cmd_key and cmd_key in SUPPORTED_SHEBANG_COMMANDS:
            command = list(SUPPORTED_SHEBANG_COMMANDS[cmd_key])
        else:
            return SingleResult(
                distro=distro,
                status=DistroStatus.ERROR,
                exit_code=None,
                duration=0.0,
                output_snippet="",
                error_message=f"Unsupported shebang command: {cmd_key}",
            )
    elif mode == ShellMode.AUTO:
        shebang_res = parsed_shebang if parsed_shebang is not None else inspect_shebang(abs_script)
        if shebang_res.status == ShebangStatus.MALFORMED:
            return SingleResult(
                distro=distro,
                status=DistroStatus.ERROR,
                exit_code=None,
                duration=0.0,
                output_snippet="",
                error_message=shebang_res.error_message or "Malformed shebang in script",
            )
        if shebang_res.status == ShebangStatus.UNSUPPORTED:
            return SingleResult(
                distro=distro,
                status=DistroStatus.ERROR,
                exit_code=None,
                duration=0.0,
                output_snippet="",
                error_message=shebang_res.error_message or "Unsupported shebang interpreter",
            )
        if shebang_res.status == ShebangStatus.RECOGNIZED:
            cmd_key = shebang_res.command_key
            if cmd_key and cmd_key in SUPPORTED_SHEBANG_COMMANDS:
                command = list(SUPPORTED_SHEBANG_COMMANDS[cmd_key])
            else:
                return SingleResult(
                    distro=distro,
                    status=DistroStatus.ERROR,
                    exit_code=None,
                    duration=0.0,
                    output_snippet="",
                    error_message=f"Unsupported shebang command: {cmd_key}",
                )
        else:
            # MISSING shebang -> auto falls back to /bin/sh
            command = list(DEFAULT_POSIX_COMMAND)

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
            diagnostic = extract_failure_diagnostic(output, exit_code=exit_code)
            return SingleResult(
                distro=distro,
                status=DistroStatus.FAIL,
                exit_code=exit_code,
                duration=duration,
                output_snippet=extract_snippet(output),
                error_message=f"Script failed with non-zero exit code: {exit_code}",
                diagnostic=diagnostic,
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
        # Best-effort container cleanup in finally block
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
    shell_mode: ShellMode | str = ShellMode.POSIX,
    client: docker.DockerClient | None = None,
) -> RunReport:
    """Run the compatibility check across all specified Linux distributions."""
    try:
        mode = ShellMode(shell_mode)
    except ValueError:
        mode = None

    parsed_shebang: ShebangParseResult | None = None
    if mode is not None and mode != ShellMode.POSIX:
        abs_script = os.path.abspath(script_path)
        if os.path.isfile(abs_script):
            parsed_shebang = inspect_shebang(abs_script)

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
            shell_mode=shell_mode,
            parsed_shebang=parsed_shebang,
        )
        results.append(res)

    total_duration = time.perf_counter() - start_total
    all_passed = all(r.status == DistroStatus.PASS for r in results) if results else True

    return RunReport(
        results=results,
        total_duration=total_duration,
        all_passed=all_passed,
    )
