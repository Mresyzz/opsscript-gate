from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest
from docker.errors import DockerException

from opsscript_gate.cli import build_parser, main, parse_matrix_argument
from opsscript_gate.models import DistroStatus, RunReport, ShellMode, SingleResult
from opsscript_gate.reporter import (
    format_github_summary,
    format_json,
    format_terminal_table,
    write_github_step_summary,
)
from opsscript_gate.runner import (
    DEFAULT_MATRIX,
    DEFAULT_POSIX_COMMAND,
    DEFAULT_TIMEOUT,
    SUPPORTED_SHEBANG_COMMANDS,
    DockerDaemonError,
    ShebangParseResult,
    ShebangStatus,
    extract_snippet,
    get_docker_client,
    inspect_shebang,
    normalize_host_path_for_docker,
    prepare_script,
    run_matrix,
    run_on_distro,
    sanitize_diagnostic_text,
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
    report = run_matrix(str(script_file), matrix=matrix, timeout=5, shell_mode="shebang", client=mock_client)

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
    assert "0.2.1" in captured.out


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
# 5. Shell Mode & Shebang Parsing Tests
# ==============================================================================

def test_inspect_shebang_matrix(tmp_path):
    # 1. Standard supported shebangs
    cases = [
        ("#!/bin/sh\nexit 0\n", ShebangStatus.RECOGNIZED, "sh"),
        ("#!/usr/bin/sh\nexit 0\n", ShebangStatus.RECOGNIZED, "sh"),
        ("#!/bin/bash\nexit 0\n", ShebangStatus.RECOGNIZED, "bash"),
        ("#!/usr/bin/bash\nexit 0\n", ShebangStatus.RECOGNIZED, "bash"),
        ("#!/usr/bin/env sh\nexit 0\n", ShebangStatus.RECOGNIZED, "sh"),
        ("#!/usr/bin/env bash\nexit 0\n", ShebangStatus.RECOGNIZED, "bash"),
        ("env sh\nexit 0\n", ShebangStatus.MISSING, None),
    ]
    for idx, (content, expected_status, expected_interp) in enumerate(cases):
        f = tmp_path / f"script_case_{idx}.sh"
        f.write_text(content, encoding="utf-8")
        res = inspect_shebang(str(f))
        assert res.status == expected_status
        assert res.interpreter == expected_interp

    # 2. CRLF shebang
    crlf_file = tmp_path / "crlf_shebang.sh"
    crlf_file.write_bytes(b"#!/usr/bin/env bash\r\necho hi\r\n")
    res_crlf = inspect_shebang(str(crlf_file))
    assert res_crlf.status == ShebangStatus.RECOGNIZED
    assert res_crlf.interpreter == "bash"

    # 3. Leading whitespace before #! must be treated as missing
    lead_space = tmp_path / "lead_space.sh"
    lead_space.write_text(" #!/bin/sh\necho hi\n", encoding="utf-8")
    assert inspect_shebang(str(lead_space)).status == ShebangStatus.MISSING

    lead_tab = tmp_path / "lead_tab.sh"
    lead_tab.write_text("\t#!/bin/bash\necho hi\n", encoding="utf-8")
    assert inspect_shebang(str(lead_tab)).status == ShebangStatus.MISSING

    # 4. Missing shebang
    no_shebang = tmp_path / "no_shebang.sh"
    no_shebang.write_text("echo 'hello world'\nexit 0\n", encoding="utf-8")
    assert inspect_shebang(str(no_shebang)).status == ShebangStatus.MISSING

    # 5. Malformed shebangs
    malformed1 = tmp_path / "malformed1.sh"
    malformed1.write_text("#!\n", encoding="utf-8")
    assert inspect_shebang(str(malformed1)).status == ShebangStatus.MALFORMED

    malformed2 = tmp_path / "malformed2.sh"
    malformed2.write_text("#!/usr/bin/env\n", encoding="utf-8")
    assert inspect_shebang(str(malformed2)).status == ShebangStatus.MALFORMED

    # 6. Unsupported shebangs (including flags and complex env forms)
    unsupported_cases = [
        "#!/usr/bin/python3\nprint('hi')\n",
        "#!/bin/zsh\nexit 0\n",
        "#!/bin/bash -e\nexit 0\n",
        "#!/usr/bin/env -S bash\nexit 0\n",
        "#!/bin/sh; rm -rf /\n",
    ]
    for idx, content in enumerate(unsupported_cases):
        f = tmp_path / f"unsupported_{idx}.sh"
        f.write_text(content, encoding="utf-8")
        assert inspect_shebang(str(f)).status == ShebangStatus.UNSUPPORTED


def test_default_and_posix_shell_mode_mock(tmp_path):
    script_file = tmp_path / "bash_script.sh"
    script_file.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b"hi\n"
    mock_client.containers.create.return_value = mock_container

    # 1. Default mode (without specifying shell_mode) -> defaults to posix (/bin/sh)
    run_on_distro(mock_client, str(script_file), "debian:12-slim")
    cmd = mock_client.containers.create.call_args[1]["command"]
    assert cmd == ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"]

    # 2. Explicit posix mode -> strictly /bin/sh regardless of #!/bin/bash
    run_on_distro(mock_client, str(script_file), "debian:12-slim", shell_mode="posix")
    cmd = mock_client.containers.create.call_args[1]["command"]
    assert cmd == ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"]


def test_shebang_mode_execution_mock(tmp_path):
    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b"hi\n"
    mock_client.containers.create.return_value = mock_container

    # 1. #!/bin/bash in shebang mode -> executes /bin/bash fixed command
    s1 = tmp_path / "s1.sh"
    s1.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    run_on_distro(mock_client, str(s1), "ubuntu:24.04", shell_mode="shebang")
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/bin/bash"]

    # 2. #!/usr/bin/bash in shebang mode -> executes /usr/bin/bash fixed command
    s2 = tmp_path / "s2.sh"
    s2.write_text("#!/usr/bin/bash\necho hi\n", encoding="utf-8")
    run_on_distro(mock_client, str(s2), "ubuntu:24.04", shell_mode="shebang")
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/usr/bin/bash"]

    # Verify that /bin/bash and /usr/bin/bash execute distinct command strings (preventing PATH-collapsing false PASS)
    assert SUPPORTED_SHEBANG_COMMANDS["/bin/bash"] != SUPPORTED_SHEBANG_COMMANDS["/usr/bin/bash"]

    # 3. #!/usr/bin/env bash in shebang mode -> executes /usr/bin/env bash
    s3 = tmp_path / "s3.sh"
    s3.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    run_on_distro(mock_client, str(s3), "ubuntu:24.04", shell_mode="shebang")
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/usr/bin/env bash"]

    # 4. #!/bin/sh in shebang mode -> executes /bin/sh
    s4 = tmp_path / "s4.sh"
    s4.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    run_on_distro(mock_client, str(s4), "debian:12-slim", shell_mode="shebang")
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/bin/sh"]

    # 5. #!/usr/bin/sh in shebang mode -> executes /usr/bin/sh
    s5 = tmp_path / "s5.sh"
    s5.write_text("#!/usr/bin/sh\necho hi\n", encoding="utf-8")
    run_on_distro(mock_client, str(s5), "debian:12-slim", shell_mode="shebang")
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/usr/bin/sh"]

    # 6. #!/usr/bin/env sh in shebang mode -> executes /usr/bin/env sh
    s6 = tmp_path / "s6.sh"
    s6.write_text("#!/usr/bin/env sh\necho hi\n", encoding="utf-8")
    run_on_distro(mock_client, str(s6), "debian:12-slim", shell_mode="shebang")
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/usr/bin/env sh"]


def test_shebang_mode_errors_no_fallback(tmp_path):
    mock_client = mock.MagicMock()

    # 1. Missing shebang -> ERROR, no container created
    s_missing = tmp_path / "missing.sh"
    s_missing.write_text("echo hi\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_missing), "ubuntu:24.04", shell_mode="shebang")
    assert res.status == DistroStatus.ERROR
    assert "No shebang found" in (res.error_message or "")
    mock_client.containers.create.assert_not_called()

    # 2. Unsupported shebang -> ERROR, no container created
    s_py = tmp_path / "py.sh"
    s_py.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_py), "ubuntu:24.04", shell_mode="shebang")
    assert res.status == DistroStatus.ERROR
    assert "Unsupported shebang interpreter" in (res.error_message or "")
    mock_client.containers.create.assert_not_called()

    # 3. Malformed shebang -> ERROR, no container created
    s_mal = tmp_path / "mal.sh"
    s_mal.write_text("#!\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_mal), "ubuntu:24.04", shell_mode="shebang")
    assert res.status == DistroStatus.ERROR
    assert "Malformed shebang" in (res.error_message or "")
    mock_client.containers.create.assert_not_called()


def test_auto_mode_semantics(tmp_path):
    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b"hi\n"
    mock_client.containers.create.return_value = mock_container

    # 1. Recognized #!/bin/bash in auto mode -> uses /bin/bash fixed command
    s_bash = tmp_path / "auto_bash.sh"
    s_bash.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_bash), "ubuntu:24.04", shell_mode="auto")
    assert res.status == DistroStatus.PASS
    assert mock_client.containers.create.call_args[1]["command"] == SUPPORTED_SHEBANG_COMMANDS["/bin/bash"]

    # 2. Missing shebang in auto mode -> falls back to /bin/sh
    s_no = tmp_path / "auto_no_shebang.sh"
    s_no.write_text("echo 'pure posix'\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_no), "ubuntu:24.04", shell_mode="auto")
    assert res.status == DistroStatus.PASS
    assert mock_client.containers.create.call_args[1]["command"] == DEFAULT_POSIX_COMMAND

    # 3. Unsupported shebang in auto mode -> MUST ERROR, NOT fall back
    mock_client.containers.create.reset_mock()
    s_unsupported = tmp_path / "auto_unsupported.sh"
    s_unsupported.write_text("#!/usr/bin/python3\nprint('hi')\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_unsupported), "ubuntu:24.04", shell_mode="auto")
    assert res.status == DistroStatus.ERROR
    assert "Unsupported shebang interpreter" in (res.error_message or "")
    mock_client.containers.create.assert_not_called()

    # 4. Malformed shebang in auto mode -> MUST ERROR, NOT fall back
    s_malformed = tmp_path / "auto_malformed.sh"
    s_malformed.write_text("#!\n", encoding="utf-8")
    res = run_on_distro(mock_client, str(s_malformed), "ubuntu:24.04", shell_mode="auto")
    assert res.status == DistroStatus.ERROR
    assert "Malformed shebang" in (res.error_message or "")
    mock_client.containers.create.assert_not_called()


def test_posix_mode_bypasses_shebang_inspection(tmp_path):
    # In posix mode, do not parse shebang at all
    script = tmp_path / "any_script.sh"
    script.write_text("gibberish\n", encoding="utf-8")

    with mock.patch("opsscript_gate.runner.inspect_shebang") as mock_inspect:
        mock_client = mock.MagicMock()
        mock_container = mock.MagicMock()
        mock_container.status = "exited"
        mock_container.attrs = {"State": {"ExitCode": 0}}
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container

        # 1. run_on_distro in posix mode
        run_on_distro(mock_client, str(script), "debian:12-slim", shell_mode="posix")
        mock_inspect.assert_not_called()

        # 2. run_matrix in posix mode
        run_matrix(str(script), matrix=["debian:12-slim", "alpine:3.20"], shell_mode="posix", client=mock_client)
        mock_inspect.assert_not_called()


def test_run_matrix_parses_shebang_once(tmp_path):
    # In run_matrix, avoid re-reading the script file on every distro for non-posix modes
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b""
    mock_client.containers.create.return_value = mock_container

    with mock.patch("opsscript_gate.runner.inspect_shebang", wraps=inspect_shebang) as spy_inspect:
        report = run_matrix(
            str(script),
            matrix=["debian:12-slim", "ubuntu:22.04", "alpine:3.20"],
            shell_mode="shebang",
            client=mock_client,
        )
        assert report.all_passed is True
        assert spy_inspect.call_count == 1


def test_sanitize_diagnostic_text():
    # Empty string
    assert sanitize_diagnostic_text("") == ""

    # Control characters, embedded CR/LF, ANSI escape, BEL
    raw = "#!/bin/sh\r\n\x00\x1b[31mecho evil\x07"
    cleaned = sanitize_diagnostic_text(raw)
    # ESC byte is absent
    assert "\x1b" not in cleaned
    # ANSI parameter residue such as "[31m" is also absent
    assert "[31m" not in cleaned
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert cleaned == "#!/bin/sh echo evil"

    # Extended CSI sequence (e.g. 256-color) is removed as a complete sequence
    extended_csi = "prefix \x1b[38;5;196mcolor\x1b[0m suffix"
    cleaned_csi = sanitize_diagnostic_text(extended_csi)
    assert "\x1b" not in cleaned_csi
    assert "[38;5;196m" not in cleaned_csi
    assert "[0m" not in cleaned_csi
    assert cleaned_csi == "prefix color suffix"

    # Additional CSI sequences (\x1b[1;31m, \x1b[?25h, etc.)
    csi_variations = "\x1b[1;31mboldred\x1b[0m \x1b[?25hcursor"
    cleaned_variations = sanitize_diagnostic_text(csi_variations)
    assert "[1;31m" not in cleaned_variations
    assert "[?25h" not in cleaned_variations
    assert cleaned_variations == "boldred cursor"

    # OSC title sequences are removed cleanly
    osc_bel = "\x1b]0;terminal title\x07echo hello"
    cleaned_osc_bel = sanitize_diagnostic_text(osc_bel)
    assert "terminal title" not in cleaned_osc_bel
    assert cleaned_osc_bel == "echo hello"

    osc_st = "\x1b]0;terminal title\x1b\\echo world"
    cleaned_osc_st = sanitize_diagnostic_text(osc_st)
    assert "terminal title" not in cleaned_osc_st
    assert cleaned_osc_st == "echo world"

    # Ordinary printable text and Unicode are preserved
    normal_text = "echo 'Hello world! 12345 äöü'"
    cleaned_normal = sanitize_diagnostic_text(normal_text)
    assert cleaned_normal == normal_text

    # Repeated whitespace is collapsed
    whitespace_text = "  a    b \t  c   \n\r  d  "
    assert sanitize_diagnostic_text(whitespace_text) == "a b c d"

    # max_length=200 returns len(result) <= 200, ends in "..."
    long_text = "#!" + "a" * 250
    truncated = sanitize_diagnostic_text(long_text, max_length=200)
    assert len(truncated) <= 200
    assert len(truncated) == 200
    assert truncated.endswith("...")
    assert truncated == "#!" + "a" * 195 + "..."

    # Small/zero max_length values do not crash and remain defensively sized
    assert sanitize_diagnostic_text("hello world", max_length=0) == ""
    assert sanitize_diagnostic_text("hello world", max_length=-5) == ""
    assert sanitize_diagnostic_text("hello world", max_length=1) == "h"
    assert sanitize_diagnostic_text("hello world", max_length=2) == "he"
    assert sanitize_diagnostic_text("hello world", max_length=3) == "..."
    assert sanitize_diagnostic_text("hello world", max_length=4) == "h..."
    assert len(sanitize_diagnostic_text("hello world", max_length=5)) <= 5


def test_missing_interpreter_compatibility_failure(tmp_path):
    # Test that a missing interpreter inside container produces a clear FAIL (e.g. exit 127)
    script_file = tmp_path / "needs_bash.sh"
    script_file.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")

    mock_client = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 127}}
    mock_container.logs.return_value = b"/bin/sh: /bin/bash: not found\n"
    mock_client.containers.create.return_value = mock_container

    result = run_on_distro(mock_client, str(script_file), "alpine:3.20", shell_mode="shebang")
    assert result.status == DistroStatus.FAIL
    assert result.exit_code == 127
    assert "not found" in result.output_snippet


def test_arbitrary_shebang_never_reaches_docker_command(tmp_path):
    # Malicious or arbitrary shebang string should never be interpolated into container command
    danger_file = tmp_path / "injection_attempt.sh"
    danger_file.write_text("#!/bin/sh; rm -rf /\necho pwn\n", encoding="utf-8")

    mock_client = mock.MagicMock()

    # In shebang mode -> rejected as unsupported
    res1 = run_on_distro(mock_client, str(danger_file), "ubuntu:24.04", shell_mode="shebang")
    assert res1.status == DistroStatus.ERROR
    mock_client.containers.create.assert_not_called()

    # In auto mode -> rejected as unsupported (not executed)
    res2 = run_on_distro(mock_client, str(danger_file), "ubuntu:24.04", shell_mode="auto")
    assert res2.status == DistroStatus.ERROR
    mock_client.containers.create.assert_not_called()

    # In posix mode -> only constant command executed
    mock_container = mock.MagicMock()
    mock_container.status = "exited"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_container.logs.return_value = b""
    mock_client.containers.create.return_value = mock_container

    run_on_distro(mock_client, str(danger_file), "ubuntu:24.04", shell_mode="posix")
    cmd = mock_client.containers.create.call_args[1]["command"]
    assert cmd == ["/bin/sh", "-c", "/bin/sh /tmp/target_script.sh </dev/null"]
    assert "; rm -rf /" not in " ".join(cmd)


def test_action_yml_input_hardening():
    # Verify that action.yml passes all inputs via env and does not interpolate directly into bash
    action_path = os.path.join(os.path.dirname(__file__), "..", "action.yml")
    assert os.path.exists(action_path)
    with open(action_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Confirm shell input is declared
    assert "shell:" in content

    # Find the run block of 'Run compatibility gate'
    assert "INPUT_SHELL: ${{ inputs.shell }}" in content
    assert "INPUT_SCRIPT_PATH: ${{ inputs.script-path }}" in content
    assert "INPUT_MATRIX: ${{ inputs.matrix }}" in content
    assert "INPUT_TIMEOUT: ${{ inputs.timeout }}" in content
    assert "INPUT_FORMAT: ${{ inputs.format }}" in content

    # Extract the run block of 'Run compatibility gate' and assert ${{ inputs. is NOT present
    gate_step = content.split("- name: Run compatibility gate")[1]
    run_block = gate_step.split("run: |")[1]
    assert "${{ inputs." not in run_block


def test_cli_shell_mode_arguments(tmp_path):
    parser = build_parser()
    # Test valid choices
    args_posix = parser.parse_args(["run", "test.sh", "--shell", "posix"])
    assert args_posix.shell == "posix"
    args_shebang = parser.parse_args(["run", "test.sh", "--shell", "shebang"])
    assert args_shebang.shell == "shebang"
    args_auto = parser.parse_args(["run", "test.sh", "--shell", "auto"])
    assert args_auto.shell == "auto"

    # Test default
    args_default = parser.parse_args(["run", "test.sh"])
    assert args_default.shell == "posix"

    # Test invalid choice raises SystemExit
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "test.sh", "--shell", "invalid_shell"])


# ==============================================================================
# 6. Integration Tests (Requires Running Docker Daemon)
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


@pytest.mark.integration
@pytest.mark.skipif(not is_docker_daemon_available(), reason="Docker daemon is not running or accessible")
def test_integration_missing_bash_alpine(tmp_path):
    # Verifies that a script with #!/bin/bash in shebang mode fails against alpine:3.20 because bash is missing
    bash_script = tmp_path / "script_bash.sh"
    bash_script.write_text("#!/bin/bash\necho 'running on bash'\nexit 0\n", encoding="utf-8")
    report = run_matrix(str(bash_script), matrix=["alpine:3.20"], timeout=30, shell_mode="shebang")
    assert report.all_passed is False
    assert len(report.results) == 1
    assert report.results[0].status == DistroStatus.FAIL
    assert report.results[0].exit_code == 127
    assert "not found" in (report.results[0].output_snippet or "").lower()
