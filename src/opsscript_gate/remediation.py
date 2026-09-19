from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RemediationRule:
    """Rule for generating conservative failure remediation hints."""
    rule_id: str
    matcher: Callable[[str | None, str | None, str], bool]
    hint: str


def _match_alpine_apt(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    return "alpine" in distro.lower() and command.lower() in ("apt", "apt-get")


def _match_debian_ubuntu_apk(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    d = distro.lower()
    return ("debian" in d or "ubuntu" in d) and command.lower() == "apk"


def _match_alpine_bash(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    return "alpine" in distro.lower() and command.lower() in ("bash", "/bin/bash", "/usr/bin/bash")


def _match_curl(distro: str | None, command: str | None, kind: str) -> bool:
    if not command:
        return False
    return command.lower().rstrip(".exe") == "curl"


def _match_wget(distro: str | None, command: str | None, kind: str) -> bool:
    if not command:
        return False
    return command.lower().rstrip(".exe") == "wget"


def _match_interpreter(distro: str | None, command: str | None, kind: str) -> bool:
    if kind == "missing_interpreter":
        return True
    if command and (command.startswith("/bin/") or command.startswith("/usr/bin/")):
        base = command.split("/")[-1]
        if base in ("bash", "sh", "zsh", "python", "python3", "perl"):
            return True
    return False


REMEDIATION_RULES: list[RemediationRule] = [
    RemediationRule(
        rule_id="alpine_apt",
        matcher=_match_alpine_apt,
        hint="Alpine normally uses apk instead of apt-get.",
    ),
    RemediationRule(
        rule_id="debian_ubuntu_apk",
        matcher=_match_debian_ubuntu_apk,
        hint="Debian/Ubuntu normally uses APT (apt-get) instead of apk.",
    ),
    RemediationRule(
        rule_id="alpine_bash",
        matcher=_match_alpine_bash,
        hint="Alpine minimal images do not include Bash by default; consider using POSIX sh or installing bash.",
    ),
    RemediationRule(
        rule_id="missing_curl",
        matcher=_match_curl,
        hint="Minimal images may not include curl; consider declaring it as a prerequisite or installing it.",
    ),
    RemediationRule(
        rule_id="missing_wget",
        matcher=_match_wget,
        hint="Minimal images may not include wget; consider declaring it as a prerequisite or installing it.",
    ),
    RemediationRule(
        rule_id="missing_interpreter",
        matcher=_match_interpreter,
        hint="Ensure the required interpreter is installed or adjust the shebang path.",
    ),
]


def generate_remediation_hint(
    distro: str | None = None,
    command: str | None = None,
    kind: str = "missing_command",
) -> str | None:
    """
    Generate a conservative, testable remediation hint for a failure.

    Uses strict conservative wording ('normally', 'may', 'consider').
    Returns None if no specific high-confidence recommendation applies.
    """
    for rule in REMEDIATION_RULES:
        if rule.matcher(distro, command, kind):
            return rule.hint
    return None
