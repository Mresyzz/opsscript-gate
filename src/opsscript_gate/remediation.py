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


def _match_debian_ubuntu_yum(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    d = distro.lower()
    return ("debian" in d or "ubuntu" in d) and command.lower() in ("yum", "dnf")


def _match_alpine_yum(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    return "alpine" in distro.lower() and command.lower() in ("yum", "dnf")


def _match_rhel_fedora_apt(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    d = distro.lower()
    is_rhel = any(name in d for name in ("fedora", "centos", "rhel", "redhat", "rocky", "alma"))
    return is_rhel and command.lower() in ("apt", "apt-get", "apk")



def _match_alpine_bash(distro: str | None, command: str | None, kind: str) -> bool:
    if not distro or not command:
        return False
    return "alpine" in distro.lower() and command.lower() in ("bash", "/bin/bash", "/usr/bin/bash")


def _match_curl(distro: str | None, command: str | None, kind: str) -> bool:
    if not command:
        return False
    normalized = command.lower().replace("\\", "/").split("/")[-1]
    if normalized.endswith(".exe"):
        normalized = normalized[:-4]
    return normalized == "curl"


def _match_wget(distro: str | None, command: str | None, kind: str) -> bool:
    if not command:
        return False
    normalized = command.lower().replace("\\", "/").split("/")[-1]
    if normalized.endswith(".exe"):
        normalized = normalized[:-4]
    return normalized == "wget"


def _match_sudo(distro: str | None, command: str | None, kind: str) -> bool:
    if not command:
        return False
    normalized = command.lower().replace("\\", "/").split("/")[-1]
    if normalized.endswith(".exe"):
        normalized = normalized[:-4]
    return normalized == "sudo"


def _match_interpreter(distro: str | None, command: str | None, kind: str) -> bool:
    if kind == "missing_interpreter":
        return True
    if command and (command.startswith("/bin/") or command.startswith("/usr/bin/")):
        base = command.split("/")[-1]
        if base in ("bash", "sh", "zsh", "python", "python3", "perl"):
            return True
    return False


# Mapping of common ops CLI command binaries to distro-specific package names.
# Supported distro families: "debian" (Debian/Ubuntu), "alpine" (Alpine Linux).
COMMON_COMMAND_PACKAGES: dict[str, dict[str, str]] = {
    "curl": {"debian": "curl", "alpine": "curl"},
    "wget": {"debian": "wget", "alpine": "wget"},
    "jq": {"debian": "jq", "alpine": "jq"},
    "git": {"debian": "git", "alpine": "git"},
    "tar": {"debian": "tar", "alpine": "tar"},
    "gzip": {"debian": "gzip", "alpine": "gzip"},
    "bzip2": {"debian": "bzip2", "alpine": "bzip2"},
    "xz": {"debian": "xz-utils", "alpine": "xz"},
    "unzip": {"debian": "unzip", "alpine": "unzip"},
    "zip": {"debian": "zip", "alpine": "zip"},
    "python": {"debian": "python3", "alpine": "python3"},
    "python3": {"debian": "python3", "alpine": "python3"},
    "pip": {"debian": "python3-pip", "alpine": "py3-pip"},
    "pip3": {"debian": "python3-pip", "alpine": "py3-pip"},
    "sudo": {"debian": "sudo", "alpine": "sudo"},
    "bash": {"debian": "bash", "alpine": "bash"},
    "make": {"debian": "build-essential", "alpine": "build-base"},
    "gcc": {"debian": "gcc", "alpine": "gcc"},
    "ca-certificates": {"debian": "ca-certificates", "alpine": "ca-certificates"},
    "openssl": {"debian": "openssl", "alpine": "openssl"},
    "nc": {"debian": "netcat-openbsd", "alpine": "netcat-openbsd"},
    "netcat": {"debian": "netcat-openbsd", "alpine": "netcat-openbsd"},
    "socat": {"debian": "socat", "alpine": "socat"},
    "envsubst": {"debian": "gettext-base", "alpine": "gettext"},
    "crontab": {"debian": "cron", "alpine": "dcron"},
    "ps": {"debian": "procps", "alpine": "procps"},
}


def detect_distro_family(distro: str | None) -> str:
    """Identify the distribution family for package manager commands."""
    if not distro:
        return "unknown"
    d = distro.lower()
    if "alpine" in d:
        return "alpine"
    if any(name in d for name in ("debian", "ubuntu", "mint")):
        return "debian"
    if any(name in d for name in ("fedora", "centos", "rhel", "redhat", "rocky", "alma")):
        return "rhel"
    return "unknown"


def resolve_package_recommendation(
    command: str | None,
    distro: str | None,
) -> tuple[str | None, str | None]:
    """
    Resolve suggested package name and actionable install command for a missing command.
    Returns (suggested_package_name, install_command).
    """
    if not command:
        return None, None
    norm_cmd = command.lower().replace("\\", "/").split("/")[-1]
    if norm_cmd.endswith(".exe"):
        norm_cmd = norm_cmd[:-4]

    packages = COMMON_COMMAND_PACKAGES.get(norm_cmd)
    if not packages:
        return None, None

    family = detect_distro_family(distro)
    package_name = packages.get(family)
    if not package_name and family in ("unknown", "rhel"):
        package_name = packages.get("debian") or packages.get("alpine")

    if not package_name:
        return None, None

    if family == "alpine":
        install_cmd = f"apk add --no-cache {package_name}"
    elif family == "debian":
        install_cmd = f"apt-get install -y {package_name}"
    elif family == "rhel":
        install_cmd = f"dnf install -y {package_name}"
    else:
        install_cmd = None

    return package_name, install_cmd


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
        rule_id="debian_ubuntu_yum",
        matcher=_match_debian_ubuntu_yum,
        hint="Debian/Ubuntu normally uses APT (apt-get) instead of yum or dnf.",
    ),
    RemediationRule(
        rule_id="alpine_yum",
        matcher=_match_alpine_yum,
        hint="Alpine normally uses apk instead of yum or dnf.",
    ),
    RemediationRule(
        rule_id="rhel_fedora_apt",
        matcher=_match_rhel_fedora_apt,
        hint="RHEL/Fedora family distributions normally use dnf or yum instead of apt-get or apk.",
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
        rule_id="missing_sudo",
        matcher=_match_sudo,
        hint="Minimal container images do not include sudo by default; containers typically run as root or require installing sudo.",
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
