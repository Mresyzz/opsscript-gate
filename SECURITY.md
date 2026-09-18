# Security Policy

## Supported Versions

Only the latest release of **OpsScript Gate** receives security updates and bug fixes.

| Version | Supported          |
| :---    | :---:              |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |
| < 0.1.0 | :x:                |

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

OpsScript Gate applies conservative container defaults when running scripts:
- **Unprivileged Execution**: Containers run with `privileged=False`, `cap_drop=["ALL"]`, and `security_opt=["no-new-privileges:true"]`.
- **Read-Only Mounting**: Target scripts are mounted read-only (`:ro`). OpsScript Gate does not mount additional host filesystem paths into test containers.
- **Resource Protection**: Containers are subject to timeouts and `SIGKILL` termination. Container removal is attempted from a `finally` block during normal Python execution paths, including failures and timeouts.
