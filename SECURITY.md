# Security Policy

## Supported Versions

Only the latest release of **OpsScript Gate** receives security updates and bug fixes.

| Version | Supported          |
| :---    | :---:              |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Reporting a Vulnerability

The security of OpsScript Gate and host container isolation is our highest priority. If you discover a security vulnerability, especially one concerning **host escape, privilege escalation, or arbitrary filesystem access**, please **do not disclose it via a public GitHub issue**.

Instead, please report security issues responsibly through one of the following channels:

1. **GitHub Private Vulnerability Reporting** (Recommended):
   - Navigate to the [Security Advisories](https://github.com/Mresyzz/opsscript-gate/security/advisories/new) page of the repository and click **Report a vulnerability**.
2. **Direct Security Contact**:
   - Send an email to `mresygg@gmail.com` with the subject prefix `[SECURITY] opsscript-gate`.

### Information to Include
- A description of the issue and its potential impact.
- Step-by-step reproduction instructions or a minimal proof-of-concept (PoC) script.
- Affected environment details (OS, Docker version, Python version).

We commit to acknowledging your report within **48 hours** and providing regular status updates regarding verification and patches.

---

## Security Boundaries & Design

OpsScript Gate enforces several design-level security guarantees:
- **Unprivileged Execution**: All containers are executed with `privileged=False`, `cap_drop=["ALL"]`, and `security_opt=["no-new-privileges:true"]`.
- **Read-Only Mounting**: Target scripts are mounted strictly with the `:ro` flag. Sensitive host directories are explicitly disallowed.
- **Resource Protection**: Containers are subject to hard timeouts and forced `SIGKILL` termination, followed by guaranteed container removal in `finally` blocks.
