# Security Policy

## Supported Versions

Only the latest release of **OpsScript Gate** receives security updates and bug fixes.

| Version | Supported          |
| :---    | :---:              |
| 0.4.x   | :white_check_mark: |
| < 0.4.0 | :x:                |

---

## Reporting a Vulnerability

Please report security issues privately rather than opening a public issue.

If you discover a vulnerability, report it through **GitHub Private Vulnerability Reporting**:
- Navigate to the [Security Advisories](https://github.com/Mresyzz/opsscript-gate/security/advisories/new) page of the repository and click **Report a vulnerability**.

### Information to Include
- A description of the issue and its potential impact.
- Step-by-step reproduction instructions or a minimal proof-of-concept (PoC) script.
- Affected environment details (OS, Docker version, Python version).

Reports will be reviewed as maintainer availability allows.

---

## Runner Security Boundaries

OpsScript Gate is not a security sandbox for untrusted code. Containers may run as the image's default user, and Docker containers still share the host kernel.

OpsScript Gate applies conservative container defaults and hardened I/O boundaries when running scripts:
- **Restricted Container Defaults**: Containers run with `privileged=False`, `cap_drop=["ALL"]`, and `security_opt=["no-new-privileges:true"]`.
- **Resource Limits & Isolation**: Enforces memory caps (`--mem-limit`, default 256m), process table caps (`--pids-limit`, default 128), and optional network isolation (`--network none`).
- **Read-Only Mounting**: Target scripts are mounted read-only (`:ro`). OpsScript Gate does not mount additional host filesystem paths into test containers.
- **Resource Protection & Hard Timeout**: Containers are subject to hard timeouts (default 60s) with `SIGKILL` termination. Container removal is performed in a `finally` block across normal, failure, and timeout execution paths.
- **Bounded Output & Rolling Buffer**: Container output capture is strictly bounded by tail lines (500) and byte caps (256 KiB) via an immediate rolling byte buffer, preventing runner memory exhaustion.
- **Untrusted Log Neutralization**: Container logs neutralize line-leading workflow commands (`[container] ::`), strip terminal ANSI/CSI/OSC sequences and dangerous C0 control characters, and apply context-sensitive Markdown/HTML escaping to protect Step Summaries.
- **Workflow Command Encoding**: OpsScript Gate's own GitHub Actions annotations (`::error`) apply strict percent-encoding for properties (`%`, `\r`, `\n`, `:`, `,`) and data (`%`, `\r`, `\n`), completely preventing command injection.
- **Bounded Streaming I/O**: Script preparation and line ending normalization operate in bounded 64 KiB chunks, and shebang line inspection is bounded to 4096 bytes.
