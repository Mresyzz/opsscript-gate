from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_action_metadata_is_valid_and_inputs_are_wired():
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "using: 'composite'" in text
    for name in ("config", "preset", "exclude", "max-scripts", "dry-run", "output", "changed-since", "packages", "repeat"):
        assert f"  {name}:" in text
    run_text = text
    for flag in ("--timeout", "--format", "--shell", "--mem-limit", "--pids-limit",
                 "--network", "--packages", "--matrix", "--jobs", "--config", "--preset", "--repeat",
                 "--max-scripts", "--output", "--exclude"):
        assert flag in run_text
    assert "json, or sarif" in text
    assert "--changed-since" in run_text


def test_test_workflow_has_valid_yaml_and_python_indent():
    text = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "        with:\n          python-version: ${{ matrix.python }}" in text
    assert "        with:\n        python-version" not in text
