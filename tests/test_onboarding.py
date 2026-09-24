import json
from pathlib import Path
from unittest.mock import patch

import pytest

from opsscript_gate.cli import main
from opsscript_gate.config import CONFIG_NAME, init_project, load_config
from opsscript_gate.discovery import discover_scripts, is_shell_script
from opsscript_gate.models import RunReport, SingleResult, DistroStatus


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "install.sh").write_text("#!/bin/sh\necho ok\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/fail.sh").write_text("#!/bin/sh\nexit 1\n")
    return tmp_path


def test_init_preview_and_no_overwrite(project, capsys):
    assert main(["init"]) == 0
    capsys.readouterr()
    with patch("opsscript_gate.cli.run_matrix") as run:
        assert main(["run", "--dry-run", "--format", "json"]) == 0
        run.assert_not_called()
    plan = json.loads(capsys.readouterr().out)
    assert plan["scripts"] == ["./install.sh"]
    assert plan["executions"] == 2
    assert plan["network"] == "none"
    assert "persist-credentials: false" in Path(".github/workflows/opsscript-gate.yml").read_text()
    original = Path(CONFIG_NAME).read_bytes()
    assert main(["init"]) == 1
    assert Path(CONFIG_NAME).read_bytes() == original


def test_init_existing_workflow_leaves_config_absent(project):
    workflow = project / ".github/workflows/opsscript-gate.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing")
    with pytest.raises(ValueError, match="overwrite"):
        init_project()
    assert not Path(CONFIG_NAME).exists()
    assert workflow.read_text() == "existing"


@pytest.mark.parametrize("config", [[], {"typo": 1}, {"timeout": True},
    {"jobs": 0}, {"exclude": "tests/*"}, {"shell": "fish"}, {"network": "host"},
    {"preset": "unknown"}, {"matrix": "alpine", "preset": "minimal"}])
def test_invalid_config(project, config):
    Path(CONFIG_NAME).write_text(json.dumps(config))
    with patch("opsscript_gate.cli.run_matrix") as run:
        assert main(["run", "--dry-run"]) == 1
        run.assert_not_called()


def test_config_cli_precedence_and_saved_plan(project, capsys):
    Path(CONFIG_NAME).write_text(json.dumps({"preset": "minimal", "timeout": 5,
        "exclude": ["tests/*"]}))
    assert main(["run", "--dry-run", "--matrix=custom:1", "--timeout", "9",
                 "--format", "json", "--output", "reports/plan.json"]) == 0
    plan = json.loads(Path("reports/plan.json").read_text())
    assert plan == json.loads(capsys.readouterr().out)
    assert plan["matrix"] == ["custom:1"]
    assert plan["timeout"] == 9


def test_preset_overrides_config_matrix(project, capsys):
    Path(CONFIG_NAME).write_text('{"matrix": "custom:1"}')
    assert main(["run", "--dry-run", "--preset", "ubuntu", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["matrix"] == ["ubuntu:22.04", "ubuntu:24.04"]


def test_discovery_limit_and_exclusions(project):
    with pytest.raises(ValueError, match="no scripts were executed"):
        discover_scripts(max_scripts=1)
    assert discover_scripts(max_scripts=1, exclude=["tests/*"]) == ["./install.sh"]
    with patch("opsscript_gate.cli.run_matrix") as run:
        assert main(["run", "--max-scripts", "1"]) == 1
        run.assert_not_called()


def test_discovery_stops_at_first_overflow(tmp_path, monkeypatch):
    for index in range(100):
        (tmp_path / f"script-{index:03}.sh").write_text("echo ok\n")
    checked = []

    def candidate(path, max_size_bytes):
        checked.append(path.name)
        return True

    monkeypatch.setattr("opsscript_gate.discovery.is_shell_script", candidate)
    with pytest.raises(ValueError, match="more than 2"):
        discover_scripts(str(tmp_path), max_scripts=2)
    assert len(checked) == 3


@pytest.mark.parametrize("flags", [["--jobs", "0"], ["--timeout", "-1"],
    ["--pids-limit", "0"], ["--network", "host"], ["--matrix", ","],
    ["--matrix", "alpine", "--preset", "minimal"], ["--config", "missing.json"]])
def test_invalid_cli_before_execution(project, flags):
    with patch("opsscript_gate.cli.run_matrix") as run:
        assert main(["run", *flags]) == 1
        run.assert_not_called()


def test_report_saved_on_failure(project):
    report = RunReport(results=[SingleResult("alpine", DistroStatus.FAIL, 1, .1)])
    with patch("opsscript_gate.cli.run_matrix", return_value=report):
        assert main(["run", "install.sh", "--format", "json", "--output", "report.json"]) == 1
    assert json.loads(Path("report.json").read_text())["all_passed"] is False


def test_output_cannot_overwrite_script(project):
    original = Path("install.sh").read_bytes()
    assert main(["run", "install.sh", "--dry-run", "--output", "install.sh"]) == 1
    assert Path("install.sh").read_bytes() == original


def test_discovery_rejects_prefix_collision_and_directory(project):
    Path("not-shell").write_text("#!/bin/shell\n")
    Path("directory.sh").mkdir()
    assert not is_shell_script(Path("not-shell"))
    assert not is_shell_script(Path("directory.sh"))


def test_discovery_does_not_follow_file_symlinks(project):
    try:
        Path("linked.sh").symlink_to(project / "install.sh")
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    assert "./linked.sh" not in discover_scripts()
