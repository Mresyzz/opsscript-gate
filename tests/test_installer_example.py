"""Exercise the downloadable workflow's inputs and generated script together."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

from opsscript_gate.cli import main


@pytest.fixture
def installer_example():
    path = Path(__file__).resolve().parents[1] / "examples/github-actions/installer-smoke.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["installer"]["steps"]
    recipe = next(step["run"] for step in steps if step.get("name") == "Prepare installer and installation check")
    inputs = next(step["with"] for step in steps if step.get("name") == "Install and verify in each distribution")
    args = ["run", inputs["script-path"]]
    for key, value in inputs.items():
        if key != "script-path":
            args.extend([f"--{key}", str(value)])
    return recipe, args, inputs


def test_downloadable_installer_inputs_are_accepted(installer_example, tmp_path, monkeypatch):
    _, args, inputs = installer_example
    monkeypatch.chdir(tmp_path)
    Path(inputs["script-path"]).write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    # This follows the copied inputs through CLI validation, without Docker.
    assert main(args + ["--dry-run"]) == 0


def docker_available():
    try:
        import docker
        client = docker.from_env()
        try:
            client.ping()
        finally:
            client.close()
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not docker_available() or not shutil.which("bash"), reason="Requires Docker and Bash")
@pytest.mark.parametrize("installed", [True, False], ids=["working-binary", "false-success"])
def test_downloadable_installer_runs_in_real_matrix(installer_example, tmp_path, monkeypatch, installed):
    recipe, args, inputs = installer_example
    monkeypatch.chdir(tmp_path)
    installer = "#!/bin/bash\n"
    if installed:
        installer += (
            'mkdir -p "$HOME/.local/bin"\n'
            'printf \'#!/bin/sh\\n[ "$1" = "--version" ] || exit 9\\necho mytool-test\\n\' '
            '> "$HOME/.local/bin/mytool"\n'
            'chmod +x "$HOME/.local/bin/mytool"\n'
        )
    # Explicit exit 0 must not skip the example's installation postcondition.
    installer += 'echo "Installation finished"\nexit 0\n'
    Path("install.sh").write_text(installer, encoding="utf-8")
    subprocess.run(["bash", "-e", "-c", recipe], check=True, timeout=10)
    assert main(args) == (0 if installed else 1)
    report = json.loads(Path(inputs["output"]).read_text(encoding="utf-8"))
    assert {result["distro"] for result in report["results"]} == set(inputs["matrix"].split(","))
    for result in report["results"]:
        assert result["status"] == ("PASS" if installed else "FAIL"), result
        assert result["exit_code"] == (0 if installed else 1), result
        if installed:
            assert "mytool-test" in result["output_snippet"]
        else:
            assert "Installer did not create" in result["output_snippet"]
