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
