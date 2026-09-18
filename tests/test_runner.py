from unittest.mock import MagicMock, patch

import pytest
import requests

from opsscript_gate.models import DistroStatus, RunReport
from opsscript_gate.reporter import format_ascii_table, format_markdown_summary, to_json
from opsscript_gate.runner import run_script_on_distros

#
# Mock / Unit Tests
#

@patch("opsscript_gate.runner.docker.from_env")
def test_run_script_success_mock(mock_docker_env):
    mock_client = MagicMock()
    mock_docker_env.return_value = mock_client

    # Mock container
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [
        b"stdout output\n",
        b"stderr output"
    ]

    report = run_script_on_distros("tests/fixtures/pass_basic.sh", ["debian:12-slim"])

    assert len(report.results) == 1
    res = report.results[0]
    assert res.image == "debian:12-slim"
    assert res.status == DistroStatus.PASS
    assert res.exit_code == 0
    assert "stdout output" in res.stdout
    assert "stderr output" in res.stderr
    assert report.all_passed is True

@patch("opsscript_gate.runner.docker.from_env")
def test_run_script_timeout_mock(mock_docker_env):
    mock_client = MagicMock()
    mock_docker_env.return_value = mock_client

    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container

    # Simulate timeout
    mock_container.wait.side_effect = requests.exceptions.ReadTimeout("Timeout")
    mock_container.logs.side_effect = [
        b"timeout logs stdout",
        b"timeout logs stderr"
    ]

    report = run_script_on_distros("tests/fixtures/fail_hang.sh", ["ubuntu:22.04"], timeout=1)

    assert len(report.results) == 1
    res = report.results[0]
    assert res.status == DistroStatus.TIMEOUT
    assert res.exit_code is None
    assert mock_container.kill.called

@patch("opsscript_gate.runner.docker.from_env")
def test_run_script_docker_exception(mock_docker_env):
    from docker.errors import DockerException
    mock_docker_env.side_effect = DockerException("Cannot connect to Docker daemon")

    report = run_script_on_distros("tests/fixtures/pass_basic.sh", ["alpine:3.20"])

    assert len(report.results) == 1
    res = report.results[0]
    assert res.status == DistroStatus.ERROR
    assert "Docker connection failed" in res.stderr

def test_reporter_formatting():
    from opsscript_gate.models import DistroStatus, SingleResult

    report = RunReport(script_path="/fake/script.sh")
    report.results.append(SingleResult("debian:12-slim", DistroStatus.PASS, 0, "ok", "", 1.23))
    report.results.append(SingleResult("alpine:3.20", DistroStatus.FAIL, 1, "", "cmd not found", 0.45))

    ascii_tbl = format_ascii_table(report)
    assert "debian:12-slim" in ascii_tbl
    assert "PASS" in ascii_tbl
    assert "FAIL" in ascii_tbl
    assert "cmd not found" in ascii_tbl

    md_summary = format_markdown_summary(report)
    assert "✅" in md_summary
    assert "❌" in md_summary
    assert "`alpine:3.20`" in md_summary

    json_out = to_json(report)
    assert "cmd not found" in json_out
    assert "false" in json_out.lower() # all_passed == False


#
# Integration Tests
#

def is_docker_available():
    import docker
    try:
        client = docker.from_env()
        client.ping()
        # Verify containers can actually run (sandboxes sometimes have dummy docker daemons that fail to create containers)
        client.containers.run("alpine:3.20", command=["echo", "test"], remove=True)
        return True
    except Exception:
        return False

@pytest.mark.integration
@pytest.mark.skipif(not is_docker_available(), reason="Docker daemon not available or cannot run containers")
def test_integration_pass_basic():
    report = run_script_on_distros("tests/fixtures/pass_basic.sh", ["alpine:3.20"])
    assert report.all_passed is True
    assert report.results[0].status == DistroStatus.PASS

@pytest.mark.integration
@pytest.mark.skipif(not is_docker_available(), reason="Docker daemon not available or cannot run containers")
def test_integration_fail_deps():
    # apt-get works on debian, fails on alpine
    report = run_script_on_distros("tests/fixtures/fail_deps.sh", ["debian:12-slim", "alpine:3.20"])
    assert report.all_passed is False

    debian_res = next(r for r in report.results if r.image == "debian:12-slim")
    assert debian_res.status == DistroStatus.PASS

    alpine_res = next(r for r in report.results if r.image == "alpine:3.20")
    assert alpine_res.status == DistroStatus.FAIL

@pytest.mark.integration
@pytest.mark.skipif(not is_docker_available(), reason="Docker daemon not available or cannot run containers")
def test_integration_fail_hang():
    # Because stdin is disconnected, `read` should return immediately with code 1 (or exit 1 because of our script logic)
    report = run_script_on_distros("tests/fixtures/fail_hang.sh", ["alpine:3.20"])
    assert report.all_passed is False
    # Depending on shell, it's either FAIL (exits 1) or TIMEOUT if it somehow hung.
    # With stdin disconnected, it shouldn't hang.
    assert report.results[0].status == DistroStatus.FAIL
