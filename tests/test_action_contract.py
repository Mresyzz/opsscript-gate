import json
import re
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
    assert "DRY_RUN_VALUE=\"$(printf '%s' \"$INPUT_DRY_RUN\" | tr '[:upper:]' '[:lower:]')\"" in text


def test_test_workflow_has_valid_yaml_and_python_indent():
    text = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "        with:\n          python-version: ${{ matrix.python }}" in text
    assert "        with:\n        python-version" not in text


def test_release_workflow_hands_main_tag_publication_to_tag_run():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'if: steps.release-check.outputs.should_tag == \'true\'' in text
    assert "The tag workflow owns release publication." in text
    assert "Treating as retry/resume of release." not in text


def test_problem_guide_structured_data_contains_faq_questions():
    text = (ROOT / "docs/command-not-found.html").read_text(encoding="utf-8")
    blocks = re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', text, re.S)
    payloads = [json.loads(block) for block in blocks]
    faq = next(payload for payload in payloads if payload.get("@type") == "FAQPage")
    names = {item["name"] for item in faq["mainEntity"]}
    assert "How do I test a shell script on Debian, Ubuntu, and Alpine?" in names
    assert "How do I diagnose apt-get not found on Alpine?" in names
    assert 'rel="canonical" href="https://mresyzz.github.io/opsscript-gate/command-not-found.html"' in text
