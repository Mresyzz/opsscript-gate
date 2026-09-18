from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest
from docker.errors import DockerException

from opsscript_gate.cli import build_parser, main, parse_matrix_argument
from opsscript_gate.models import DistroStatus, RunReport, SingleResult
from opsscript_gate.reporter import (
    format_github_summary,
    format_json,
    format_terminal_table,
    write_github_step_summary,
)
from opsscript_gate.runner import (
    DEFAULT_MATRIX,
    DEFAULT_TIMEOUT,
    DockerDaemonError,
    extract_snippet,
    get_docker_client,
    normalize_host_path_for_docker,
    prepare_script,
    run_matrix,
    run_on_distro,
)


# ==============================================================================
# 1. Models & Utilities Tests
# ==============================================================================

def test_models_serialization():
    res1 = SingleResult(
        distro="debian:12-slim",
        status=DistroStatus.PASS,
        exit_code=0,
        duration=1.2345,
        output_snippet="all good",
    )
    res2 = SingleResult(
        distro="alpine:3.20",
        status=DistroStatus.FAIL,
        exit_code=127,
        duration=0.5,
        output_snippet="not found",
        error_message="Exit 127",
    )
    report = RunReport(results=[res1, res2], total_duration=1.735)

    assert not report.all_passed
    assert len(report.results) == 2

    d = report.to_dict()
    assert d["all_passed"] is False
    assert d["total_duration"] == 1.735
    assert d["results"][0]["distro"] == "debian:12-slim"
    assert d["results"][0]["status"] == "PASS"
    assert d["results"][1]["exit_code"] == 127


def test_models_all_passed():
    res1 = SingleResult(
        distro="debian:12-slim",
        status=DistroStatus.PASS,
        exit_code=0,
        duration=1.0,
    )
    report = RunReport(results=[res1], total_duration=1.0)
    assert report.all_passed is True


def test_extract_snippet():
    assert extract_snippet("") == ""
    short_text = "line 1\nline 2"
    assert extract_snippet(short_text, max_lines=5) == short_text

    long_lines = [f"line {i}" for i in range(30)]
    long_text = "\n".join(long_lines)
    snippet = extract_snippet(long_text, max_lines=15)
    extracted = snippet.splitlines()
    assert len(extracted) == 15
    assert extracted[0] == "line 15"
    assert extracted[-1] == "line 29"


def test_normalize_host_path_for_docker():
    path = r"C:\Users\Admin\script.sh"
    normalized = normalize_host_path_for_docker(path)
    assert "\\" not in normalized
    assert normalized.endswith("/script.sh")


def test_crlf_defense(tmp_path):
    # Create a script with CRLF line endings
    crlf_script = tmp_path / "script_crlf.sh"
    crlf_script.write_bytes(b"#!/bin/sh\r\necho hello\r\nexit 0\r\n")

    mount_path, temp_file = prepare_script(str(crlf_script))
    try:
        assert temp_file is not None
        assert os.path.exists(mount_path)
        with open(mount_path, "rb") as f:
            content = f.read()
        # CRLF should be converted to LF
        assert b"\r\n" not in content
        assert b"\n" in content
    finally:
        if temp_file:
            temp_file.close()
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)

    # Clean LF script should not create a temporary file
    lf_script = tmp_path / "script_lf.sh"
    lf_script.write_bytes(b"#!/bin/sh\necho hello\nexit 0\n")
    clean_mount_path, no_temp_file = prepare_script(str(lf_script))
    assert no_temp_file is None
    assert clean_mount_path == os.path.abspath(str(lf_script))


# ==============================================================================
# 2. Docker Client & Runner Unit Tests (Mocked)
# ==============================================================================

def test_get_docker_client_failure():
    with mock.patch("docker.from_env", side_effect=DockerException("Connection refused")):
        with pytest.raises(DockerDaemonError) as excinfo:
            get_docker_client()
        assert "Cannot connect to Docker daemon" in str(excinfo.value)


def test_run_on_distro_missing_script(tmp_path):
    mock_client = mock.MagicMock()
    missing_file = str(tmp_path / "non_existent.sh")
    result = run_on_distro(mock_client, missing_file, "debian:12-slim")
    assert result.status == DistroStatus.ERROR
    assert "does not exist" in (result.error_message or "")


def test_run_on_distro_pass_mock(tmp_path):
    script_file = tmp_path / "test.sh"
    script_file.write_text("#!/bin/sh\necho OK\nexit 0\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b"OK\n"

    mock_client.containers.create.return_value = mock_container

    result = run_on_distro(mock_client, str(script_file), "debian:12-slim", timeout=10)

    assert result.status == DistroStatus.PASS
    assert result.exit_code == 0
    assert "OK" in result.output_snippet
    assert result.error_message is None

    # Verify security constraints on container creation
    create_kwargs = mock_client.containers.create.call_args[1]
    assert create_kwargs["privileged"] is False
    assert create_kwargs["stdin_open"] is False
    assert create_kwargs["tty"] is False
    assert create_kwargs["environment"]["DEBIAN_FRONTEND"] == "noninteractive"
    assert create_kwargs["environment"]["CI"] == "true"
    assert create_kwargs["security_opt"] == ["no-new-privileges:true"]
    # Verify command adheres to /bin/sh compatibility red-line
    assert create_kwargs["command"] == ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"]
    # Verify read-only mount
    volumes = create_kwargs["volumes"]
    for src, bind_info in volumes.items():
        assert bind_info["bind"] == "/tmp/target_script.sh"
        assert bind_info["mode"] == "ro"

    # Verify zero-zombie container removal
    mock_container.remove.assert_called_once_with(force=True)


def test_run_on_distro_fail_mock(tmp_path):
    script_file = tmp_path / "test_fail.sh"
    script_file.write_text("#!/bin/sh\napt-get: not found\nexit 127\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 127}}
    mock_container.logs.return_value = b"sh: line 2: apt-get: not found\n"

    mock_client.containers.create.return_value = mock_container

    result = run_on_distro(mock_client, str(script_file), "alpine:3.20", timeout=10)

    assert result.status == DistroStatus.FAIL
    assert result.exit_code == 127
    assert "apt-get: not found" in result.output_snippet
    assert "127" in (result.error_message or "")
    mock_container.remove.assert_called_once_with(force=True)


def test_run_on_distro_timeout_kill_mock(tmp_path):
    script_file = tmp_path / "hang.sh"
    script_file.write_text("#!/bin/sh\nsleep 100\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "running"
    mock_container.logs.return_value = b"still sleeping..."

    mock_client.containers.create.return_value = mock_container

    # Mock time.perf_counter to simulate timeout
    with mock.patch("time.perf_counter", side_effect=[0.0, 0.1, 10.0, 10.5, 11.0]):
        result = run_on_distro(mock_client, str(script_file), "ubuntu:24.04", timeout=5, poll_interval=0.01)

    assert result.status == DistroStatus.TIMED_OUT
    assert result.exit_code is None
    assert "timed out" in (result.error_message or "").lower()
    # Verify container.kill() was called upon timeout
    mock_container.kill.assert_called_once()
    # Verify container.remove(force=True) was called
    mock_container.remove.assert_called_once_with(force=True)


def test_run_matrix_aggregation(tmp_path):
    script_file = tmp_path / "matrix_test.sh"
    script_file.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b"Success"
    mock_client.containers.create.return_value = mock_container

    matrix = ["debian:12-slim", "ubuntu:22.04"]
    report = run_matrix(str(script_file), matrix=matrix, timeout=5, client=mock_client)

    assert report.all_passed is True
    assert len(report.results) == 2
    assert report.results[0].distro == "debian:12-slim"
    assert report.results[1].distro == "ubuntu:22.04"


# ==============================================================================
# 3. Reporter Formatting Tests
# ==============================================================================

def test_reporter_terminal_table():
    r1 = SingleResult("debian:12-slim", DistroStatus.PASS, 0, 1.2, "OK")
    r2 = SingleResult("alpine:3.20", DistroStatus.FAIL, 127, 0.4, "cmd not found", "Exit 127")
    report = RunReport([r1, r2], total_duration=1.6)

    table_output = format_terminal_table(report)
    assert "Distro" in table_output
    assert "debian:12-slim" in table_output
    assert "alpine:3.20" in table_output
    assert "Result: FAILED" in table_output
    assert "cmd not found" in table_output


def test_reporter_github_summary():
    r1 = SingleResult("debian:12-slim", DistroStatus.PASS, 0, 1.2)
    r2 = SingleResult("ubuntu:22.04", DistroStatus.TIMED_OUT, None, 60.0, "hanging...", "Timed out")
    report = RunReport([r1, r2], total_duration=61.2)

    md = format_github_summary(report)
    assert "## 🛡️ OpsScript Gate Compatibility Report" in md
    assert "CHECKS FAILED" in md
    assert "| `debian:12-slim` | ✅ PASS | `0` | `1.20s` |" in md
    assert "| `ubuntu:22.04` | ⏱️ TIMED_OUT | `N/A` | `60.00s` |" in md
    assert "<details><summary><b>[TIMED_OUT] ubuntu:22.04</b></summary>" in md


def test_reporter_json():
    r1 = SingleResult("debian:12-slim", DistroStatus.PASS, 0, 1.0)
    report = RunReport([r1], total_duration=1.0)
    json_str = format_json(report)
    data = json.loads(json_str)
    assert data["all_passed"] is True
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "PASS"


def test_write_github_step_summary(tmp_path):
    summary_file = tmp_path / "step_summary.md"
    r1 = SingleResult("debian:12-slim", DistroStatus.PASS, 0, 1.0)
    report = RunReport([r1], total_duration=1.0)

    with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
        success = write_github_step_summary(report)
        assert success is True
        content = summary_file.read_text(encoding="utf-8")
        assert "## 🛡️ OpsScript Gate Compatibility Report" in content


# ==============================================================================
# 4. CLI Argument Parsing & Execution Tests
# ==============================================================================

def test_parse_matrix_argument():
    assert parse_matrix_argument(None) == DEFAULT_MATRIX
    assert parse_matrix_argument("") == DEFAULT_MATRIX
    assert parse_matrix_argument("debian:12-slim, alpine:3.20") == ["debian:12-slim", "alpine:3.20"]


def test_cli_help(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])


def test_cli_run_pass(tmp_path):
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    fake_report = RunReport(
        results=[SingleResult("debian:12-slim", DistroStatus.PASS, 0, 0.5)],
        total_duration=0.5,
        all_passed=True,
    )

    with mock.patch("opsscript_gate.cli.run_matrix", return_value=fake_report):
        exit_code = main(["run", str(script), "--format", "json"])
        assert exit_code == 0


def test_cli_run_failure(tmp_path):
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")

    fake_report = RunReport(
        results=[SingleResult("alpine:3.20", DistroStatus.FAIL, 1, 0.5)],
        total_duration=0.5,
        all_passed=False,
    )

    with mock.patch("opsscript_gate.cli.run_matrix", return_value=fake_report):
        exit_code = main(["run", str(script)])
        assert exit_code == 1


def test_cli_run_file_not_found():
    exit_code = main(["run", "non_existent_path_xyz.sh"])
    assert exit_code == 1


def test_cli_run_docker_daemon_error(tmp_path):
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with mock.patch("opsscript_gate.cli.run_matrix", side_effect=DockerDaemonError("Docker unreachable")):
        exit_code = main(["run", str(script)])
        assert exit_code == 1


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "0.1.0" in captured.out


def test_cli_format_markdown_and_table(tmp_path, capsys):
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    fake_report = RunReport(
        results=[SingleResult("debian:12-slim", DistroStatus.PASS, 0, 0.5)],
        total_duration=0.5,
        all_passed=True,
    )

    with mock.patch("opsscript_gate.cli.run_matrix", return_value=fake_report):
        code_md = main(["run", str(script), "--format", "markdown"])
        assert code_md == 0
        captured_md = capsys.readouterr()
        assert "## 🛡️ OpsScript Gate" in captured_md.out

        code_tbl = main(["run", str(script), "--format", "table"])
        assert code_tbl == 0
        captured_tbl = capsys.readouterr()
        assert "debian:12-slim" in captured_tbl.out


def test_run_on_distro_pulls_image_if_not_found(tmp_path):
    from docker.errors import ImageNotFound

    script_file = tmp_path / "test_pull.sh"
    script_file.write_text("#!/bin/sh\necho Pulled\nexit 0\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b"Pulled\n"

    # First call to create raises ImageNotFound, second call returns mock_container
    mock_client.containers.create.side_effect = [
        ImageNotFound("Image not present"),
        mock_container,
    ]

    result = run_on_distro(mock_client, str(script_file), "alpine:3.20", timeout=10)
    assert result.status == DistroStatus.PASS
    mock_client.images.pull.assert_called_once_with("alpine:3.20")
    assert mock_client.containers.create.call_count == 2


def test_fixtures_posix_shebang_compliance():
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    for name in ["pass_basic.sh", "fail_deps.sh", "fail_hang.sh"]:
        path = os.path.join(fixtures_dir, name)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            assert first_line == "#!/bin/sh", f"{name} must strictly use #!/bin/sh for Alpine compatibility"
            content = f.read()
            assert "/bin/bash" not in content, f"{name} must not hardcode /bin/bash"


# ==============================================================================
# 5. Integration Tests (Requires Running Docker Daemon)
# ==============================================================================

def is_docker_daemon_available() -> bool:
    try:
        import docker
        c = docker.from_env()
        c.ping()
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not is_docker_daemon_available(), reason="Docker daemon is not running or accessible")
def test_integration_pass_basic():
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "pass_basic.sh")
    report = run_matrix(fixture, matrix=["alpine:3.20"], timeout=30)
    assert report.all_passed is True
    assert report.results[0].status == DistroStatus.PASS


@pytest.mark.integration
@pytest.mark.skipif(not is_docker_daemon_available(), reason="Docker daemon is not running or accessible")
def test_integration_fail_deps_alpine():
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "fail_deps.sh")
    report = run_matrix(fixture, matrix=["alpine:3.20"], timeout=30)
    assert report.all_passed is False
    assert report.results[0].status == DistroStatus.FAIL
    assert report.results[0].exit_code == 127
