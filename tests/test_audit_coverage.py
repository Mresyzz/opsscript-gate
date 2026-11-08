from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from opsscript_gate.config import load_config, validate_memory_limit, validate_packages
from opsscript_gate.discovery import discover_changed_scripts
from opsscript_gate.models import DistroStatus, MultiScriptReport, RunReport, SingleResult
from opsscript_gate.remediation import _match_interpreter, generate_remediation_hint
from opsscript_gate.reporter import (
    format_multi_sarif,
    format_sarif,
    sanitize_display_text,
    sanitize_workflow_text,
)


# ==============================================================================
# 1. config.py 单元测试与边界校验
# ==============================================================================

def test_validate_packages_valid():
    # 正常列表
    assert validate_packages(["curl", "git", "python3"]) == ["curl", "git", "python3"]

    # 重复元素去重（保持顺序）
    assert validate_packages(["curl", "git", "curl", "git", "vim"]) == ["curl", "git", "vim"]

    # 首尾空白修剪
    assert validate_packages(["  curl  ", " git "]) == ["curl", "git"]

    # 合法特殊字符：+, ., _, :, -
    valid_special = ["g++", "python3.10", "libssl-dev", "pkg:arch", "test_pkg"]
    assert validate_packages(valid_special) == valid_special


def test_validate_packages_invalid_types():
    # 顶层必须是 list
    for invalid in ["curl", 123, None, {"pkg": "curl"}, ("curl",)]:
        with pytest.raises(ValueError, match="packages must be a list of package names"):
            validate_packages(invalid)

    # 列表元素必须全为 str
    for invalid_list in [[123], [None], ["curl", None], ["curl", 456]]:
        with pytest.raises(ValueError, match="packages must be a list of package names"):
            validate_packages(invalid_list)


def test_validate_packages_invalid_names():
    # 空白字符包名
    for empty in [[""], ["   "], ["curl", ""]]:
        with pytest.raises(ValueError, match="packages must contain nonempty package names"):
            validate_packages(empty)

    # 非法注入或不符合正则字符
    invalid_names = [
        ["curl;rm -rf /"],
        ["curl&&echo"],
        ["curl|bash"],
        ["curl`id`"],
        ["curl$(whoami)"],
        ["curl pkg"],
        ["-startwithhyphen"],
        [".startwithdot"],
    ]
    for bad in invalid_names:
        with pytest.raises(ValueError, match="packages must contain nonempty package names"):
            validate_packages(bad)


def test_validate_memory_limit_valid():
    # 常见合法格式（支持 b/k/m/g 以及 kb/mb/gb 后缀）
    assert validate_memory_limit("256m") == "256m"
    assert validate_memory_limit("1g") == "1g"
    assert validate_memory_limit("512M") == "512M"
    assert validate_memory_limit("2G") == "2G"
    assert validate_memory_limit("256mb") == "256mb"
    # 首尾空白修剪
    assert validate_memory_limit("  256m  ") == "256m"


def test_validate_memory_limit_invalid():
    # 非字符串类型
    for non_str in [256, None, ["256m"], 1.5]:
        with pytest.raises(ValueError, match="mem_limit must be a positive Docker memory limit"):
            validate_memory_limit(non_str)

    # 空白字符串
    for blank in ["", "   "]:
        with pytest.raises(ValueError, match="mem_limit must be a positive Docker memory limit"):
            validate_memory_limit(blank)

    # 非正数或非法单位/格式
    invalid_mem = ["0m", "-100m", "invalid", "100x", "256tb", "10.5.2m", "NaNm"]
    for bad in invalid_mem:
        with pytest.raises(ValueError, match="mem_limit must be a positive Docker memory limit"):
            validate_memory_limit(bad)


def test_load_config_file_not_found(tmp_path):
    # 显式传入不存在的配置文件路径应抛出 ValueError
    missing_file = tmp_path / "does_not_exist.json"
    with pytest.raises(ValueError, match="Cannot load"):
        load_config(str(missing_file))

    # 传入 None 且默认配置文件不存在时应返回空字典
    with mock.patch("pathlib.Path.exists", return_value=False):
        assert load_config(None) == {}


def test_load_config_oversized(tmp_path):
    large_config = tmp_path / "large.json"
    large_config.write_bytes(b"{" + b" " * (256 * 1024) + b"}")
    with pytest.raises(ValueError, match="configuration exceeds 256 KiB limit"):
        load_config(str(large_config))


def test_load_config_not_a_json_object(tmp_path):
    array_config = tmp_path / "array.json"
    array_config.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="Project configuration must be a JSON object"):
        load_config(str(array_config))


def test_load_config_unknown_keys(tmp_path):
    cfg = tmp_path / "unknown.json"
    cfg.write_text('{"bad_key": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown configuration keys: bad_key"):
        load_config(str(cfg))


def test_load_config_matrix_and_preset_conflict(tmp_path):
    cfg = tmp_path / "conflict.json"
    cfg.write_text('{"matrix": "alpine:3.20", "preset": "minimal"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Configure either matrix or preset, not both"):
        load_config(str(cfg))


# ==============================================================================
# 2. discovery.py discover_changed_scripts 异常与边界测试
# ==============================================================================

def test_discover_changed_scripts_invalid_since(tmp_path):
    # 空白、横线开头、包含空格的 revision 均应被拦截
    for bad_since in ["", "   ", "-flag", "--all", "HEAD ^", "v1.0 2"]:
        with pytest.raises(ValueError, match="changed-since must name a Git revision"):
            discover_changed_scripts(root_dir=str(tmp_path), since=bad_since)


def test_discover_changed_scripts_git_not_found(tmp_path):
    with mock.patch("subprocess.run", side_effect=FileNotFoundError("git: command not found")):
        with pytest.raises(ValueError, match="changed-since requires Git to be installed"):
            discover_changed_scripts(root_dir=str(tmp_path), since="main")


def test_discover_changed_scripts_git_error(tmp_path):
    error = subprocess.CalledProcessError(
        returncode=128,
        cmd=["git", "diff"],
        stderr=b"fatal: ambiguous argument 'unknown_rev...HEAD': unknown revision\n",
    )
    with mock.patch("subprocess.run", side_effect=error):
        with pytest.raises(
            ValueError,
            match=r"Cannot compare Git revision 'unknown_rev' with HEAD: fatal: ambiguous argument",
        ):
            discover_changed_scripts(root_dir=str(tmp_path), since="unknown_rev")


def test_discover_changed_scripts_overflow(tmp_path):
    script1 = tmp_path / "script1.sh"
    script1.write_text("#!/bin/sh\necho 1\n", encoding="utf-8")
    script2 = tmp_path / "script2.sh"
    script2.write_text("#!/bin/sh\necho 2\n", encoding="utf-8")

    # Git 返回两个相对路径（null 字节分隔）
    fake_stdout = b"script1.sh\0script2.sh\0"
    completed = subprocess.CompletedProcess(
        args=["git", "diff"],
        returncode=0,
        stdout=fake_stdout,
        stderr=b"",
    )
    with mock.patch("subprocess.run", return_value=completed):
        with pytest.raises(ValueError, match="Changed files include more than 1 shell scripts, exceeding limit"):
            discover_changed_scripts(root_dir=str(tmp_path), since="HEAD^", max_scripts=1)


# ==============================================================================
# 3. reporter.py 文本消毒与 SARIF 全状态规则映射测试
# ==============================================================================

def test_sanitize_display_text():
    # 空字符串
    assert sanitize_display_text("") == ""

    # 回车换行归一化
    assert sanitize_display_text("line1\r\nline2\rline3\n") == "line1\nline2\nline3\n"

    # 清除不可打印 C0 控制字符（保留 \t, \n），清除 C1 控制字符与 Unicode Cf（格式控制符）
    raw = "clean\x00text\x07with\x08tab\tand\nnewline\x1b[31m\u202e\u200b"
    sanitized = sanitize_display_text(raw)
    assert "\x00" not in sanitized
    assert "\x07" not in sanitized
    assert "\x08" not in sanitized
    assert "\x1b" not in sanitized
    assert "\u202e" not in sanitized
    assert "\u200b" not in sanitized
    assert "\t" in sanitized
    assert "\n" in sanitized
    assert "cleantextwithtab\tand\nnewline[31m" == sanitized


def test_sanitize_workflow_text():
    # 保留 \r, \n, \t 用于工作流指令转义，同时清除危险的控制字符和 Cf
    raw = "workflow\r\n\t\x00alert\x1b\u202e"
    sanitized = sanitize_workflow_text(raw)
    assert "\r\n\t" in sanitized
    assert "\x00" not in sanitized
    assert "\x1b" not in sanitized
    assert "\u202e" not in sanitized


def test_sarif_all_status_rules():
    # 构建包含 FAIL, TIMED_OUT, ERROR, FLAKY 以及 PASS 的报表
    results = [
        SingleResult(distro="debian:12-slim", status=DistroStatus.PASS, duration=0.1, exit_code=0),
        SingleResult(distro="alpine:3.20", status=DistroStatus.FAIL, duration=0.2, exit_code=1, error_message="Command failed"),
        SingleResult(distro="ubuntu:22.04", status=DistroStatus.TIMED_OUT, duration=60.0, exit_code=None, error_message="Execution timed out"),
        SingleResult(distro="ubuntu:24.04", status=DistroStatus.ERROR, duration=0.05, exit_code=None, error_message="Container startup error"),
        SingleResult(distro="fedora:40", status=DistroStatus.FLAKY, duration=0.3, exit_code=1, error_message="Flaky run detected"),
    ]
    report = RunReport(results=results, total_duration=60.65)
    sarif_raw = format_sarif(report, script_path="scripts/test.sh")
    sarif_data = json.loads(sarif_raw)

    rule_ids = [res["ruleId"] for res in sarif_data["runs"][0]["results"]]
    # PASS 不应出现在 SARIF 结果中，其余 4 种状态对应 OSG001 ~ OSG004
    assert rule_ids == ["OSG001", "OSG002", "OSG003", "OSG004"]

    # 验证 MultiScriptReport 中的 format_multi_sarif
    multi_report = MultiScriptReport(
        reports={"scripts/test.sh": report},
        total_duration=60.65,
    )
    multi_sarif_raw = format_multi_sarif(multi_report)
    multi_sarif_data = json.loads(multi_sarif_raw)
    multi_rule_ids = [res["ruleId"] for res in multi_sarif_data["runs"][0]["results"]]
    assert multi_rule_ids == ["OSG001", "OSG002", "OSG003", "OSG004"]


# ==============================================================================
# 4. remediation.py 解释器与绝对路径匹配测试
# ==============================================================================

def test_remediation_interpreter_matchers():
    # kind == "missing_interpreter" 无论命令如何都应匹配
    assert _match_interpreter("debian:12-slim", "any_cmd", "missing_interpreter") is True

    # 常见解释器路径匹配
    for valid_interp in [
        "/bin/bash",
        "/bin/sh",
        "/bin/zsh",
        "/usr/bin/bash",
        "/usr/bin/python",
        "/usr/bin/python3",
        "/usr/bin/perl",
    ]:
        assert _match_interpreter("alpine:3.20", valid_interp, "missing_command") is True

    # 非解释器或非绝对标准路径不应匹配
    for invalid_cmd in ["python3", "bash", "/usr/bin/custom_binary", "/opt/bin/python"]:
        assert _match_interpreter("alpine:3.20", invalid_cmd, "missing_command") is False


def test_remediation_hint_for_interpreter():
    # kind == "missing_interpreter" 优先级高于普通命令
    hint_kind = generate_remediation_hint(
        distro="ubuntu:22.04",
        command="/usr/bin/python3",
        kind="missing_interpreter",
    )
    assert hint_kind == "Ensure the required interpreter is installed or adjust the shebang path."

    # 未被包名映射接管的解释器路径（如 zsh）应触发解释器修复建议
    hint_zsh = generate_remediation_hint(
        distro="ubuntu:22.04",
        command="/usr/bin/zsh",
        kind="missing_command",
    )
    assert hint_zsh == "Ensure the required interpreter is installed or adjust the shebang path."

    # 包含在解释器规则中的路径（如 python3），generate_remediation_hint 保持保守提示
    hint_py = generate_remediation_hint(
        distro="ubuntu:22.04",
        command="/usr/bin/python3",
        kind="missing_command",
    )
    assert hint_py == "Ensure the required interpreter is installed or adjust the shebang path."

    # resolve_package_recommendation 则针对该命令提供精准的跨发行版包名与安装命令
    from opsscript_gate.remediation import resolve_package_recommendation
    pkg_py, cmd_py = resolve_package_recommendation("/usr/bin/python3", "ubuntu:22.04")
    assert pkg_py == "python3"
    assert "apt-get install -y python3" in cmd_py

    # 不匹配时返回 None
    assert generate_remediation_hint(distro="ubuntu:22.04", command="/usr/bin/unknown", kind="missing_command") is None


# ==============================================================================
# 5. 发现的新问题与防御加固测试
# ==============================================================================

def test_is_shell_script_unreadable_file(tmp_path):
    from opsscript_gate.discovery import is_shell_script

    unreadable = tmp_path / "denied.sh"
    unreadable.write_text("#!/bin/sh\necho test\n", encoding="utf-8")

    # 模拟读权限被拒绝（PermissionError）
    with mock.patch("builtins.open", side_effect=PermissionError("Permission denied")):
        assert is_shell_script(unreadable) is False


def test_run_on_distro_cleans_up_own_temp_file_on_error(tmp_path):
    import os
    from opsscript_gate.runner import run_on_distro

    # 创建包含 CRLF 的脚本以触发 prepare_script 生成临时文件
    script = tmp_path / "crlf_pkg_fail.sh"
    script.write_bytes(b"#!/bin/sh\r\necho hello\r\n")

    created_temp_files = []
    original_named_temp = __import__("tempfile").NamedTemporaryFile

    def spy_temp_file(*args, **kwargs):
        tf = original_named_temp(*args, **kwargs)
        created_temp_files.append(tf.name)
        return tf

    with mock.patch("tempfile.NamedTemporaryFile", side_effect=spy_temp_file):
        with mock.patch("opsscript_gate.runner._wrap_with_package_setup", side_effect=ValueError("Setup generation failed")):
            result = run_on_distro(
                client=mock.MagicMock(),
                script_path=str(script),
                distro="debian:12-slim",
                packages=["curl"],
            )
            assert result.status == DistroStatus.ERROR
            assert "Setup generation failed" in (result.error_message or "")

    # 验证创建的临时文件在返回后已经被完全清理，没有发生泄漏
    assert len(created_temp_files) >= 1
    for temp_path in created_temp_files:
        assert not os.path.exists(temp_path)


def test_run_matrix_directory_and_missing_script_preflight(tmp_path):
    from opsscript_gate.runner import run_matrix

    missing = str(tmp_path / "does_not_exist.sh")
    report_missing = run_matrix(missing, matrix=["debian:12-slim"])
    assert report_missing.all_passed is False
    assert len(report_missing.results) == 1
    assert "Target script does not exist" in (report_missing.results[0].error_message or "")

    is_dir = str(tmp_path)
    report_dir = run_matrix(is_dir, matrix=["debian:12-slim"])
    assert report_dir.all_passed is False
    assert len(report_dir.results) == 1
    assert "not a regular file" in (report_dir.results[0].error_message or "")


def test_publish_output_preserves_posix_newline(tmp_path, capsys):
    from opsscript_gate.cli import publish_output

    out_file = tmp_path / "report_clean.txt"
    publish_output("hello\nworld", str(out_file))

    # 验证无论在何种操作系统下写入，都严格保持标准 LF 换行，绝无 \r\n 污染
    raw_bytes = out_file.read_bytes()
    assert raw_bytes == b"hello\nworld\n"
    assert b"\r" not in raw_bytes


# ==============================================================================
# 6. 跨发行版包名推荐与自动安装建议功能测试
# ==============================================================================

def test_detect_distro_family():
    from opsscript_gate.remediation import detect_distro_family

    assert detect_distro_family("alpine:3.20") == "alpine"
    assert detect_distro_family("debian:12-slim") == "debian"
    assert detect_distro_family("ubuntu:22.04") == "debian"
    assert detect_distro_family("fedora:40") == "rhel"
    assert detect_distro_family("centos:7") == "rhel"
    assert detect_distro_family("rocky:9") == "rhel"
    assert detect_distro_family("archlinux:latest") == "unknown"
    assert detect_distro_family(None) == "unknown"


def test_resolve_package_recommendation():
    from opsscript_gate.remediation import resolve_package_recommendation

    # 跨发行版包名差异测试：pip 在 Alpine 为 py3-pip，在 Debian 为 python3-pip
    alp_pip, alp_cmd = resolve_package_recommendation("pip", "alpine:3.20")
    assert alp_pip == "py3-pip"
    assert alp_cmd == "apk add --no-cache py3-pip"

    deb_pip, deb_cmd = resolve_package_recommendation("pip", "debian:12-slim")
    assert deb_pip == "python3-pip"
    assert deb_cmd == "apt-get install -y python3-pip"

    # xz 在 Debian 为 xz-utils，在 Alpine 为 xz
    deb_xz, deb_xz_cmd = resolve_package_recommendation("xz", "ubuntu:24.04")
    assert deb_xz == "xz-utils"
    assert deb_xz_cmd == "apt-get install -y xz-utils"

    alp_xz, alp_xz_cmd = resolve_package_recommendation("xz", "alpine:3.20")
    assert alp_xz == "xz"
    assert alp_xz_cmd == "apk add --no-cache xz"

    # 常见运维命令 jq, curl, git
    jq_pkg, jq_cmd = resolve_package_recommendation("jq", "alpine:3.20")
    assert jq_pkg == "jq"
    assert jq_cmd == "apk add --no-cache jq"

    # 未知命令或空输入
    assert resolve_package_recommendation("unknown_custom_tool", "debian:12-slim") == (None, None)
    assert resolve_package_recommendation(None, "debian:12-slim") == (None, None)


def test_resolve_package_recommendation_install_commands():
    from opsscript_gate.remediation import resolve_package_recommendation, generate_remediation_hint

    # 针对 jq 的精准包名与安装命令
    pkg_alp, cmd_alp = resolve_package_recommendation("jq", distro="alpine:3.20")
    assert pkg_alp == "jq"
    assert cmd_alp == "apk add --no-cache jq"

    pkg_deb, cmd_deb = resolve_package_recommendation("jq", distro="debian:12-slim")
    assert pkg_deb == "jq"
    assert cmd_deb == "apt-get install -y jq"

    # 确保原有包管理器误用规则依然优先且行为稳定
    hint_apt = generate_remediation_hint(distro="alpine:3.20", command="apt-get", kind="missing_command")
    assert hint_apt == "Alpine normally uses apk instead of apt-get."


def test_failure_diagnostic_and_sarif_suggested_package():
    from opsscript_gate.models import FailureDiagnostic, SingleResult, RunReport, DistroStatus
    from opsscript_gate.reporter import format_sarif

    diag = FailureDiagnostic(
        kind="missing_command",
        command="jq",
        message="command not found: jq",
        suggested_package="jq",
    )
    d_dict = diag.to_dict()
    assert d_dict.get("suggested_package") == "jq"

    res = SingleResult(
        distro="alpine:3.20",
        status=DistroStatus.FAIL,
        exit_code=127,
        duration=0.1,
        diagnostic=diag,
    )
    report = RunReport(results=[res], total_duration=0.1)
    sarif = json.loads(format_sarif(report, script_path="deploy.sh"))
    props = sarif["runs"][0]["results"][0]["properties"]
    assert props.get("command") == "jq"
    assert props.get("suggestedPackage") == "jq"


# ==============================================================================
# 7. 缺陷深度修复专项回归测试
# ==============================================================================

def test_remediation_matchers_with_absolute_paths():
    from opsscript_gate.remediation import generate_remediation_hint

    # 验证全路径命令（如 /usr/bin/apt-get, /sbin/apk, /bin/yum, /usr/local/bin/bash）均能精准命中
    assert generate_remediation_hint(
        distro="alpine:3.20", command="/usr/bin/apt-get", kind="missing_command"
    ) == "Alpine normally uses apk instead of apt-get."

    assert generate_remediation_hint(
        distro="ubuntu:22.04", command="/sbin/apk", kind="missing_command"
    ) == "Debian/Ubuntu normally uses APT (apt-get) instead of apk."

    assert generate_remediation_hint(
        distro="debian:12-slim", command="/usr/bin/yum", kind="missing_command"
    ) == "Debian/Ubuntu normally uses APT (apt-get) instead of yum or dnf."

    assert generate_remediation_hint(
        distro="alpine:3.20", command="/usr/bin/yum", kind="missing_command"
    ) == "Alpine normally uses apk instead of yum or dnf."

    assert generate_remediation_hint(
        distro="fedora:40", command="/usr/bin/apt-get", kind="missing_command"
    ) == "RHEL/Fedora family distributions normally use dnf or yum instead of apt-get or apk."

    assert generate_remediation_hint(
        distro="alpine:3.20", command="/usr/local/bin/bash", kind="missing_command"
    ) == "Alpine minimal images do not include Bash by default; consider using POSIX sh or installing bash."


def test_rhel_package_recommendations():
    from opsscript_gate.remediation import resolve_package_recommendation

    # RHEL 原生包名映射
    pkg_make, cmd_make = resolve_package_recommendation("make", distro="fedora:40")
    assert pkg_make == "make"
    assert cmd_make == "dnf install -y make"

    pkg_xz, cmd_xz = resolve_package_recommendation("xz", distro="rocky:9")
    assert pkg_xz == "xz"
    assert cmd_xz == "dnf install -y xz"

    pkg_nc, cmd_nc = resolve_package_recommendation("nc", distro="centos:7")
    assert pkg_nc == "nmap-ncat"
    assert cmd_nc == "dnf install -y nmap-ncat"

    pkg_cron, cmd_cron = resolve_package_recommendation("crontab", distro="rhel:9")
    assert pkg_cron == "cronie"
    assert cmd_cron == "dnf install -y cronie"

    # 全路径命令也可以正常识别
    pkg_curl, cmd_curl = resolve_package_recommendation("/usr/bin/curl", distro="fedora:40")
    assert pkg_curl == "curl"
    assert cmd_curl == "dnf install -y curl"


def test_package_setup_rhel_package_managers():
    from opsscript_gate.runner import _wrap_with_package_setup

    wrapped = _wrap_with_package_setup(["/bin/sh", "-c", "echo 1"], ["curl", "jq"])
    cmd_str = " ".join(wrapped)
    # 验证生成的预装包装命令已包含 dnf、microdnf、yum 支持
    assert "command -v dnf" in cmd_str
    assert "command -v microdnf" in cmd_str
    assert "command -v yum" in cmd_str


def test_run_report_empty_explicit_all_passed():
    from opsscript_gate.models import RunReport, MultiScriptReport

    # 验证空结果集但显式指定 all_passed=False 时不被篡改为 True
    report = RunReport(results=[], all_passed=False)
    assert report.all_passed is False

    multi = MultiScriptReport(reports={}, all_passed=False)
    assert multi.all_passed is False

    # 默认值依然保持 True
    assert RunReport().all_passed is True
    assert MultiScriptReport().all_passed is True


def test_discovery_matches_exclude_directory():
    from opsscript_gate.discovery import _matches_exclude

    # 验证目录名排除规则能够正确匹配目录本身及目录下所有文件
    assert _matches_exclude("tests/foo.sh", ["tests"]) is True
    assert _matches_exclude("tests/sub/bar.sh", ["tests"]) is True
    assert _matches_exclude("tests/foo.sh", ["tests/"]) is True
    assert _matches_exclude("tests/foo.sh", ["./tests/"]) is True
    assert _matches_exclude("other/foo.sh", ["tests"]) is False


# ==============================================================================
# 8. 扩展诊断引擎与生态增强测试（Exit 126、OOM、Amazon/Oracle Linux、Outputs）
# ==============================================================================

def test_extract_failure_diagnostic_permission_denied():
    from opsscript_gate.runner import extract_failure_diagnostic

    # Bash 格式: bash: ./install.sh: Permission denied
    out_bash = "bash: ./install.sh: Permission denied\n"
    diag_bash = extract_failure_diagnostic(out_bash, exit_code=126, distro="debian:12-slim")
    assert diag_bash is not None
    assert diag_bash.kind == "permission_denied"
    assert diag_bash.command == "./install.sh"
    assert "permission denied" in diag_bash.message
    assert "chmod +x" in diag_bash.hint

    # Dash 格式带行号: sh: 1: ./install.sh: Permission denied
    out_dash = "sh: 1: ./install.sh: Permission denied\n"
    diag_dash = extract_failure_diagnostic(out_dash, exit_code=126, distro="ubuntu:24.04")
    assert diag_dash is not None
    assert diag_dash.kind == "permission_denied"
    assert diag_dash.command == "./install.sh"
    assert diag_dash.line == 1

    # Ash 格式: /bin/sh: line 3: ./helper.sh: Permission denied
    out_ash = "/bin/sh: line 3: ./helper.sh: Permission denied\n"
    diag_ash = extract_failure_diagnostic(out_ash, exit_code=126, distro="alpine:3.20")
    assert diag_ash is not None
    assert diag_ash.kind == "permission_denied"
    assert diag_ash.command == "./helper.sh"
    assert diag_ash.line == 3

    # 非 126 退出码不会误报 permission_denied
    assert extract_failure_diagnostic(out_bash, exit_code=1, distro="debian:12-slim") is None


def test_extract_failure_diagnostic_exec_format_error():
    from opsscript_gate.runner import extract_failure_diagnostic

    # Bash 格式: bash: ./binary: cannot execute binary file: Exec format error
    out_bash = "bash: ./binary: cannot execute binary file: Exec format error\n"
    diag = extract_failure_diagnostic(out_bash, exit_code=126, distro="alpine:3.20")
    assert diag is not None
    assert diag.kind == "exec_format_error"
    assert diag.command == "./binary"
    assert "cannot execute binary" in diag.message
    assert "incompatible" in diag.hint

    # Dash 格式: sh: 1: ./binary: Exec format error
    out_dash = "sh: 1: ./binary: Exec format error\n"
    diag_dash = extract_failure_diagnostic(out_dash, exit_code=126, distro="ubuntu:22.04")
    assert diag_dash is not None
    assert diag_dash.kind == "exec_format_error"
    assert diag_dash.line == 1


def test_remediation_amazon_and_oracle_linux():
    from opsscript_gate.remediation import detect_distro_family, resolve_package_recommendation, generate_remediation_hint

    # 验证 Amazon Linux
    assert detect_distro_family("amazonlinux:2023") == "rhel"
    assert detect_distro_family("amazonlinux:2") == "rhel"
    assert detect_distro_family("public.ecr.aws/amazonlinux/amazonlinux:2023") == "rhel"

    # 验证 Oracle Linux
    assert detect_distro_family("oraclelinux:9") == "rhel"
    assert detect_distro_family("ol:8") == "rhel"

    # 验证在 Amazon Linux 下的包推荐
    pkg, cmd = resolve_package_recommendation("curl", "amazonlinux:2023")
    assert pkg == "curl"
    assert cmd == "dnf install -y curl"

    # 验证在 Amazon Linux 误用 apt-get 的提示
    hint = generate_remediation_hint(distro="amazonlinux:2023", command="apt-get", kind="missing_command")
    assert "RHEL/Fedora family distributions normally use dnf or yum" in hint


def test_run_report_count_properties():
    from opsscript_gate.models import RunReport, MultiScriptReport, SingleResult, DistroStatus

    res_pass = SingleResult("debian:12-slim", DistroStatus.PASS, 0, 0.1)
    res_fail = SingleResult("alpine:3.20", DistroStatus.FAIL, 127, 0.2)
    res_timeout = SingleResult("ubuntu:22.04", DistroStatus.TIMED_OUT, None, 1.0)

    report = RunReport([res_pass, res_fail, res_timeout])
    assert report.total_count == 3
    assert report.passed_count == 1
    assert report.failed_count == 2
    assert report.all_passed is False

    multi = MultiScriptReport({
        "s1.sh": RunReport([res_pass]),
        "s2.sh": RunReport([res_fail]),
    })
    assert multi.total_scripts_count == 2
    assert multi.passed_scripts_count == 1
    assert multi.failed_scripts_count == 1
    assert multi.all_passed is False


def test_reporter_rendering_suggested_package_and_new_diagnostics():
    from opsscript_gate.models import SingleResult, DistroStatus, FailureDiagnostic, RunReport
    from opsscript_gate.reporter import format_markdown_compatibility_card, format_terminal_table, format_sarif
    import json

    diag = FailureDiagnostic(
        kind="permission_denied",
        command="./install.sh",
        message="permission denied: ./install.sh",
        line=4,
        hint="Target script lacks executable permissions.",
        suggested_package=None,
    )
    result = SingleResult("alpine:3.20", DistroStatus.FAIL, 126, 0.5, diagnostic=diag)
    report = RunReport([result])

    card = format_markdown_compatibility_card(report, "deploy.sh")
    assert "Permission denied: `./install.sh` (line 4)" in card

    # 包含 suggested_package
    diag_pkg = FailureDiagnostic(
        kind="missing_command",
        command="jq",
        message="command not found: jq",
        suggested_package="jq",
        hint="Consider installing jq.",
    )
    result_pkg = SingleResult("debian:12-slim", DistroStatus.FAIL, 127, 0.2, diagnostic=diag_pkg)
    report_pkg = RunReport([result_pkg])

    card_pkg = format_markdown_compatibility_card(report_pkg, "script.sh")
    assert "Package: `jq`" in card_pkg
    assert "**Suggested Package:** `jq`" in card_pkg

    # Terminal 报告验证
    terminal = format_terminal_table(report_pkg)
    assert "(suggested package: jq)" in terminal

    # SARIF diagnosticKind 验证
    sarif = json.loads(format_sarif(report, "deploy.sh"))
    props = sarif["runs"][0]["results"][0]["properties"]
    assert props["diagnosticKind"] == "permission_denied"


# ==============================================================================
# 11. 环境变量安全注入与工作空间目录挂载专项测试 (v0.9.6)
# ==============================================================================

def test_validate_env_valid_and_invalid():
    from opsscript_gate.config import validate_env

    # 合法情况
    assert validate_env({"FOO": "bar", "_BAZ_123": "val"}) == {"FOO": "bar", "_BAZ_123": "val"}
    assert validate_env({}) == {}

    # 非字典拒绝
    with pytest.raises(ValueError, match="env must be a JSON object"):
        validate_env(["FOO=bar"])

    # 非法 key 命名拒绝
    with pytest.raises(ValueError, match="Invalid environment variable name '123FOO'"):
        validate_env({"123FOO": "bar"})

    with pytest.raises(ValueError, match="Invalid environment variable name 'FOO-BAR'"):
        validate_env({"FOO-BAR": "bar"})

    # 非字符串 value 拒绝
    with pytest.raises(ValueError, match="Environment variable 'FOO' value must be a string"):
        validate_env({"FOO": 123})


def test_validate_workdir_valid_and_invalid(tmp_path):
    from opsscript_gate.config import validate_workdir

    # 合法目录
    sub_dir = tmp_path / "my_workspace"
    sub_dir.mkdir()
    assert validate_workdir(str(sub_dir)) == str(sub_dir.resolve())

    # 不存在目录拒绝
    with pytest.raises(ValueError, match="workdir directory does not exist"):
        validate_workdir(str(tmp_path / "non_existent"))

    # 指向普通文件拒绝
    file_path = tmp_path / "regular.sh"
    file_path.write_text("#!/bin/sh\n")
    with pytest.raises(ValueError, match="workdir is not a directory"):
        validate_workdir(str(file_path))

    # 空或非字符串拒绝
    with pytest.raises(ValueError, match="workdir must be a nonempty path string"):
        validate_workdir("")
    with pytest.raises(ValueError, match="workdir must be a nonempty path string"):
        validate_workdir(123)


def test_config_env_and_workdir_support(tmp_path):
    from opsscript_gate.config import load_config
    import json

    ws = tmp_path / "ws"
    ws.mkdir()
    cfg_file = tmp_path / ".opsscript-gate.json"
    cfg_file.write_text(json.dumps({
        "env": {"APP_PORT": "8080", "APP_ENV": "staging"},
        "workdir": str(ws),
    }))

    loaded = load_config(str(cfg_file))
    assert loaded["env"] == {"APP_PORT": "8080", "APP_ENV": "staging"}
    assert loaded["workdir"] == str(ws.resolve())


def test_parse_env_arguments_cli(monkeypatch):
    from opsscript_gate.cli import parse_env_arguments

    monkeypatch.setenv("EXISTING_VAR", "host_value")

    # KEY=VALUE 格式
    res = parse_env_arguments(["FOO=123", "BAR=abc=def"])
    assert res == {"FOO": "123", "BAR": "abc=def"}

    # 单独 KEY（从宿主机环境变量获取）
    res_host = parse_env_arguments(["EXISTING_VAR", "NON_EXISTING"])
    assert res_host["EXISTING_VAR"] == "host_value"
    assert res_host["NON_EXISTING"] == ""

    # 多行输入
    res_multiline = parse_env_arguments(["A=1\nB=2\n\nC=3"])
    assert res_multiline == {"A": "1", "B": "2", "C": "3"}

    # 优先级合并：命令行覆盖 base_env
    res_merge = parse_env_arguments(["A=cli_val", "B=2"], base_env={"A": "base_val", "C": "3"})
    assert res_merge == {"A": "cli_val", "B": "2", "C": "3"}

    # 非法名称抛错
    with pytest.raises(ValueError, match="Invalid environment variable name: 'BAD-NAME'"):
        parse_env_arguments(["BAD-NAME=1"])


def test_cli_output_overwrites_protected_case_insensitive(tmp_path, monkeypatch):
    from opsscript_gate.cli import _output_overwrites_protected
    from pathlib import Path

    file_a = tmp_path / "README.md"
    file_a.write_text("hello")

    # 同一路径
    assert _output_overwrites_protected(file_a, [file_a]) is True

    # 验证在 Windows 平台下大小写不敏感碰撞保护
    monkeypatch.setattr("os.name", "nt")
    file_lower = tmp_path / "readme.md"
    assert _output_overwrites_protected(file_lower, [file_a]) is True

    # 未受保护的文件
    file_other = tmp_path / "other.txt"
    assert _output_overwrites_protected(file_other, [file_a]) is False


def test_run_matrix_with_env_and_workdir_mock(tmp_path):
    from opsscript_gate.runner import run_matrix
    from unittest.mock import MagicMock

    script = tmp_path / "test.sh"
    script.write_text("#!/bin/sh\necho ok\n")

    ws = tmp_path / "my_workdir"
    ws.mkdir()

    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"ok\n"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_client.containers.create.return_value = mock_container

    report = run_matrix(
        script_path=str(script),
        matrix=["debian:12-slim"],
        client=mock_client,
        env={"TEST_KEY": "test_val"},
        workdir=str(ws),
    )

    assert report.all_passed is True
    create_call = mock_client.containers.create.call_args[1]

    # 验证环境变量合并
    assert create_call["environment"]["TEST_KEY"] == "test_val"
    assert create_call["environment"]["CI"] == "true"
    assert create_call["environment"]["DEBIAN_FRONTEND"] == "noninteractive"

    # 验证工作区只读挂载与工作目录配置
    assert create_call["working_dir"] == "/workspace"
    found_ws_mount = False
    for host_vol, cfg in create_call["volumes"].items():
        if cfg["bind"] == "/workspace":
            assert cfg["mode"] == "ro"
            found_ws_mount = True
    assert found_ws_mount is True


def test_cli_dry_run_displays_env_and_workdir(tmp_path, capsys):
    from opsscript_gate.cli import main
    import json

    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\n")

    ws = tmp_path / "workspace"
    ws.mkdir()

    code = main([
        "run",
        str(script),
        "--dry-run",
        "--format", "json",
        "--env", "VAR_A=1",
        "--workdir", str(ws),
    ])
    assert code == 0
    captured = capsys.readouterr().out
    plan = json.loads(captured)
    assert plan["env"] == {"VAR_A": "1"}
    assert plan["workdir"] == str(ws.resolve())


def test_expanded_remediation_packages():
    from opsscript_gate.remediation import resolve_package_recommendation

    for cmd, deb_expected, alp_expected in [
        ("find", "findutils", "findutils"),
        ("xargs", "findutils", "findutils"),
        ("grep", "grep", "grep"),
        ("sed", "sed", "sed"),
        ("awk", "gawk", "gawk"),
        ("diff", "diffutils", "diffutils"),
        ("patch", "patch", "patch"),
        ("ssh", "openssh-client", "openssh-client"),
        ("rsync", "rsync", "rsync"),
        ("htop", "htop", "htop"),
    ]:
        pkg_deb, _ = resolve_package_recommendation(cmd, "debian:12-slim")
        assert pkg_deb == deb_expected, f"Failed for debian {cmd}"
        pkg_alp, _ = resolve_package_recommendation(cmd, "alpine:3.20")
        assert pkg_alp == alp_expected, f"Failed for alpine {cmd}"


# ==============================================================================
# 12. Fail-Fast 快速失败与 dash / ash 原生解释器专项测试 (v0.9.7)
# ==============================================================================

def test_shebang_dash_and_ash_support(tmp_path):
    from opsscript_gate.runner import inspect_shebang, ShebangStatus, _resolve_shell_command, ShellMode

    # 1. 直接 /bin/dash 与 /usr/bin/dash
    dash_script = tmp_path / "dash_script"
    dash_script.write_text("#!/bin/dash\necho hello\n")
    res_dash = inspect_shebang(str(dash_script))
    assert res_dash.status == ShebangStatus.RECOGNIZED
    assert res_dash.interpreter == "dash"
    assert res_dash.command_key == "/bin/dash"
    cmd_dash, err_dash = _resolve_shell_command(ShellMode.SHEBANG, res_dash)
    assert err_dash is None
    assert "/bin/dash /tmp/target_script.sh </dev/null" in cmd_dash[2]

    # 2. 直接 /bin/ash 与 /usr/bin/env ash
    ash_script = tmp_path / "ash_script"
    ash_script.write_text("#!/usr/bin/env ash\necho hello\n")
    res_ash = inspect_shebang(str(ash_script))
    assert res_ash.status == ShebangStatus.RECOGNIZED
    assert res_ash.interpreter == "ash"
    assert res_ash.command_key == "/usr/bin/env ash"
    cmd_ash, err_ash = _resolve_shell_command(ShellMode.SHEBANG, res_ash)
    assert err_ash is None
    assert "/usr/bin/env ash /tmp/target_script.sh </dev/null" in cmd_ash[2]


def test_workdir_relative_script_mount_and_command(tmp_path):
    from opsscript_gate.runner import run_on_distro
    from unittest.mock import MagicMock

    ws = tmp_path / "repo_root"
    ws.mkdir()
    sub_dir = ws / "scripts" / "nested"
    sub_dir.mkdir(parents=True)
    script_file = sub_dir / "setup.sh"
    script_file.write_text("#!/bin/sh\necho test\n")

    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"test\n"
    mock_container.attrs = {"State": {"ExitCode": 0}}
    mock_client.containers.create.return_value = mock_container

    res = run_on_distro(
        client=mock_client,
        script_path=str(script_file),
        distro="debian:12-slim",
        workdir=str(ws),
    )
    assert res.status.value == "PASS"

    create_call = mock_client.containers.create.call_args[1]
    # 容器命令中的脚本路径应自动映射至 /workspace/scripts/nested/setup.sh
    cmd_str = create_call["command"][2]
    assert "/workspace/scripts/nested/setup.sh" in cmd_str

    # 验证 volume bind 路径亦为 /workspace/scripts/nested/setup.sh
    bind_targets = [v["bind"] for v in create_call["volumes"].values()]
    assert "/workspace" in bind_targets
    assert "/workspace/scripts/nested/setup.sh" in bind_targets


def test_fail_fast_multi_script(tmp_path, capsys):
    from opsscript_gate.cli import main
    from unittest.mock import patch
    from opsscript_gate.models import RunReport, SingleResult, DistroStatus

    s1 = tmp_path / "a_fail.sh"
    s1.write_text("#!/bin/sh\nexit 1\n")
    s2 = tmp_path / "b_pass.sh"
    s2.write_text("#!/bin/sh\nexit 0\n")

    executed_scripts = []

    def fake_run_checked_matrix(args, script_path, matrix):
        executed_scripts.append(script_path)
        if "a_fail" in script_path:
            return RunReport([SingleResult("debian:12-slim", DistroStatus.FAIL, 1, 0.1)])
        return RunReport([SingleResult("debian:12-slim", DistroStatus.PASS, 0, 0.1)])

    with patch("opsscript_gate.cli.discover_scripts", return_value=[str(s1), str(s2)]):
        with patch("opsscript_gate.cli.run_checked_matrix", side_effect=fake_run_checked_matrix):
            # 开启 fail-fast：第 1 个脚本失败后，第 2 个脚本不应被执行
            code = main(["run", "--fail-fast"])
            assert code == 1
            assert len(executed_scripts) == 1
            assert executed_scripts[0] == str(s1)


def test_fail_fast_matrix_repeat(tmp_path):
    from opsscript_gate.runner import run_matrix
    from unittest.mock import MagicMock

    script = tmp_path / "test.sh"
    script.write_text("#!/bin/sh\n")

    mock_client = MagicMock()
    mock_container = MagicMock()
    # 模拟第一次执行就失败
    mock_container.wait.return_value = {"StatusCode": 1}
    mock_container.logs.return_value = b"failed\n"
    mock_container.attrs = {"State": {"ExitCode": 1}}
    mock_client.containers.create.return_value = mock_container

    # 设置 repeat=5, jobs=1, fail_fast=True
    report = run_matrix(
        script_path=str(script),
        matrix=["debian:12-slim"],
        client=mock_client,
        repeat=5,
        jobs=1,
        fail_fast=True,
    )
    assert report.all_passed is False
    # fail_fast 生效：containers.create 仅被调用 1 次，而非 5 次
    assert mock_client.containers.create.call_count == 1


def test_config_fail_fast_setting(tmp_path, capsys):
    from opsscript_gate.cli import main
    import json

    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\n")

    cfg_file = tmp_path / ".opsscript-gate.json"
    cfg_file.write_text(json.dumps({
        "fail_fast": True,
    }))

    code = main([
        "run",
        str(script),
        "--config", str(cfg_file),
        "--dry-run",
        "--format", "json",
    ])
    assert code == 0
    captured = capsys.readouterr().out
    plan = json.loads(captured)
    assert plan["fail_fast"] is True



