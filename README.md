# OpsScript Gate

> **ShellCheck tells you if your script looks portable. OpsScript Gate checks if it actually runs there.**

[![CI](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml)
[![Demo](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml)
[![PyPI](https://img.shields.io/pypi/v/opsscript-gate)](https://pypi.org/project/opsscript-gate/)
[![Python Versions](https://img.shields.io/pypi/pyversions/opsscript-gate)](https://pypi.org/project/opsscript-gate/)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-OpsScript%20Gate-blue?logo=github&color=2088FF)](https://github.com/marketplace/actions/opsscript-gate)
[![Release](https://img.shields.io/github/v/release/Mresyzz/opsscript-gate?color=green)](https://github.com/Mresyzz/opsscript-gate/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Supported Distros](https://img.shields.io/badge/matrix-Debian%20%7C%20Ubuntu%20%7C%20Alpine-orange.svg)](#default-test-matrix)

**OpsScript Gate** is a drop-in runtime compatibility gate for Linux shell scripts. It executes your scripts inside unprivileged Debian, Ubuntu, and Alpine containers before merge, catching environment-specific runtime failures, missing interpreters, and package-manager assumptions that static analysis cannot detect.

---

## ⚡ 30-Second Quickstart

### In GitHub Actions (Zero Config)

Drop this minimal workflow into `.github/workflows/shell-compat.yml`:

```yaml
name: Shell Compatibility Gate
on: [pull_request, push]

jobs:
  compat:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: Mresyzz/opsscript-gate@v0.4.1
```

> **Zero Config**: If `script-path` is omitted, OpsScript Gate automatically discovers shell scripts in your repository and tests them concurrently!

Or test a specific script with custom execution modes:

```yaml
      - uses: Mresyzz/opsscript-gate@v0.4.1
        with:
          script-path: scripts/install.sh
          shell: auto
          jobs: 4
```

### In Local Terminal (CLI)

Requires Python 3.10+ and a running local Docker engine:

```bash
# Install from PyPI
pip install opsscript-gate

# Run against a specific script
opsscript-gate run ./scripts/install.sh

# Or auto-discover scripts across your repository
opsscript-gate run
```

---

## 🎯 Reviewer-First Experience: What It Produces

Every run of OpsScript Gate generates clean, actionable feedback right where developers and reviewers need it:

### 1. Line-Level GitHub Annotations
When a failure occurs, OpsScript Gate flags the exact script line on your Pull Request's **Files Changed** view with high-confidence diagnostics and conservative remediation hints:

```text
::error file=scripts/setup.sh,line=4,title=OpsScript Gate: [alpine:3.20] command not found: apt-get::command not found: apt-get — Alpine normally uses apk instead of apt-get.
```

### 2. GitHub Step Summary Compatibility Card
A beautifully formatted markdown summary is automatically posted to `$GITHUB_STEP_SUMMARY`:

```markdown
## 🛡️ OpsScript Gate Compatibility Report

**Target Script**: `scripts/setup.sh`  
**Status**: ❌ **CHECKS FAILED (3/4 Passed)**  
**Total Duration**: `1.24s`

### 📊 Compatibility Matrix

| Distribution | Status | Exit Code | Time | Diagnostic & Recommendation |
| :--- | :---: | :---: | :---: | :--- |
| `debian:12-slim` | ✅ PASS | `0` | `0.42s` | OK |
| `ubuntu:22.04` | ✅ PASS | `0` | `0.38s` | OK |
| `ubuntu:24.04` | ✅ PASS | `0` | `0.35s` | OK |
| `alpine:3.20` | ❌ FAIL | `127` | `0.19s` | ⚠️ Missing command: `apt-get` (line 4)<br>💡 *Alpine normally uses apk instead of apt-get.* |

<details>
<summary>📋 <b>Copyable Markdown (Click to expand & copy to PR / Issue)</b></summary>
...
</details>
```

---

## 🔍 Example: What Static Analysis Misses

Consider this clean deployment script:

```bash
#!/bin/sh
set -e
echo "Fetching package information..."
apt-get --version
```

Running `shellcheck` reports **0 errors, 0 warnings** because the syntax is syntactically valid POSIX shell.

However, when verified with **OpsScript Gate**:

```text
+----------------+----------+-----------+----------+------------------------------------+
| Distro         | Status   | Exit Code | Duration | Details                            |
+----------------+----------+-----------+----------+------------------------------------+
| debian:12-slim | PASS     | 0         | 0.42s    | OK                                 |
| ubuntu:22.04   | PASS     | 0         | 0.38s    | OK                                 |
| ubuntu:24.04   | PASS     | 0         | 0.35s    | OK                                 |
| alpine:3.20    | FAIL     | 127       | 0.19s    | command not found: apt-get (line 4)|
+----------------+----------+-----------+----------+------------------------------------+
Total duration: 0.58s | Result: FAILED

Remediation Recommendations:
  * [alpine:3.20] Alpine normally uses apk instead of apt-get.

============================================================
Failed Distributions - Output Snippets (last 15 lines):
============================================================

--- [alpine:3.20] (FAIL) ---
sh: line 4: apt-get: not found
```

**Why it failed:** Alpine Linux is musl/BusyBox-based and uses `apk`, not `apt-get`. OpsScript Gate catches the missing command (`exit code 127`) and gives you the exact line number and conservative remediation hint before deployment.

---

## 🛡️ Why OpsScript Gate?

### OpsScript Gate vs ShellCheck vs Custom CI Matrix

| Capability | OpsScript Gate | ShellCheck | Handwritten CI Matrix |
| :--- | :---: | :---: | :---: |
| **Runtime execution** | **Yes** | No (Static AST only) | Yes |
| **Real distro environments** | **Yes (Debian, Ubuntu, Alpine)** | No | Yes |
| **Preconfigured defaults** | **Yes** | Yes | Requires custom workflow configuration |
| **Hardened container defaults** | **Built-in (`ro`, `cap_drop`, resource limits)** | N/A | User-defined |
| **Anti-hang stdin protection** | **Built-in (`</dev/null`, noninteractive)** | No | User-defined |
| **Line-Level Annotations & Hints** | **Built-in (Zero config)** | Static warnings | User-defined |
| **Parallel Matrix Execution** | **Built-in (`--jobs`)** | N/A | Manual matrix config |

- **ShellCheck** is indispensable for static analysis (syntax, quoting, SC warnings). OpsScript Gate complements it by testing actual execution behavior in real distributions.
- **Handwritten CI Matrix** requires maintaining complex Docker configurations, volume mounts, timeout guards, and log parsers across every project. OpsScript Gate packages this into a single check.

---

## 🔒 Security Boundaries & Hardened Isolation

OpsScript Gate is not a security sandbox for untrusted code. Containers may run as the image's default user, and Docker containers still share the host kernel.

OpsScript Gate applies conservative, restricted container defaults when running scripts:

1. **Restricted Container Defaults**:
   - Containers run with `privileged=False`.
   - All Linux capabilities are dropped: `cap_drop=["ALL"]`.
   - Privilege escalation is disabled: `security_opt=["no-new-privileges:true"]`.
2. **Resource Constraints**:
   - Memory limits enforced per container (`--mem-limit`, default: `256m`).
   - Process caps enforced to prevent fork bombs (`--pids-limit`, default: `128`).
   - Network isolation configurable (`--network bridge` or `--network none`).
3. **Read-Only Target Mount**:
   - The tested script is mounted read-only (`:ro`) at `/tmp/target_script.sh`.
   - No host directories or sensitive sockets are mounted into test containers.
4. **Anti-Hang Deadlock Defense**:
   - Disables TTY and stdin (`stdin_open=False`, `tty=False`).
   - Disconnects standard input: `/bin/sh -c "... /tmp/target_script.sh </dev/null"`.
   - Injects `DEBIAN_FRONTEND=noninteractive` and `CI=true`. Interactive prompts (`read -p`) fail immediately instead of hanging CI runners.
5. **Hard Timeout & Container Cleanup**:
   - Enforces configurable timeout (default: 60s). Timed-out containers are sent `SIGKILL` and marked `TIMED_OUT`.
   - Container removal is attempted from a `finally` block in normal, failure, and timeout execution paths.
6. **Bounded Output & Memory Protection**:
   - Captures container logs using an immediate rolling byte buffer capped at 256 KiB (`MAX_CAPTURED_LOG_BYTES`) and tail limited to 500 lines (`MAX_LOG_TAIL_LINES`), which bounds retained container log data to reduce memory-exhaustion risk.
7. **Untrusted Log Neutralization & Terminal Defense**:
   - Neutralizes line-leading workflow commands (`[container] ::`) to prevent forged GitHub Actions annotations in CI runners.
   - Strips ANSI escape sequences and dangerous C0 control characters, and normalizes carriage returns (`\r`) to defeat terminal line overwrite spoofing.
   - Employs context-sensitive escaping (`escape_inline_code`, `escape_markdown_text`, `escape_markdown_table_cell`, `escape_html_text`, `format_safe_code_fence`) to prevent Step Summary layout disruptions.
8. **Command Injection Defense**:
   - OpsScript Gate's own annotations (`::error`) apply strict percent-encoding for all properties and message bodies, preventing workflow command injection.
9. **Bounded Streaming CRLF & Shebang Defense**:
   - Stream-normalizes carriage returns in 64 KiB chunks, preserving lone CR bytes and bounds shebang parsing to 4096 bytes without whole-file memory allocation.
   - Pre-normalizes scripts once before parallel matrix runs, sharing a read-only prepared path across worker threads.

---

## 📦 Default Test Matrix

| Image | Distribution | Focus |
| :--- | :--- | :--- |
| `debian:12-slim` | Debian 12 (Bookworm) | Minimal glibc + APT base |
| `ubuntu:22.04` | Ubuntu 22.04 LTS (Jammy) | Enterprise long-term support baseline |
| `ubuntu:24.04` | Ubuntu 24.04 LTS (Noble) | Modern glibc, updated coreutils & defaults |
| `alpine:3.20` | Alpine Linux 3.20 | Minimal musl libc + BusyBox /bin/sh environment |

Customize the matrix at any time via `--matrix` or Action input `matrix`.

---

## 🛠️ CLI Reference

```text
usage: opsscript-gate run [-h] [--matrix MATRIX] [-j JOBS] [--timeout TIMEOUT]
                          [--format {table,markdown,json}]
                          [--shell {posix,shebang,auto}]
                          [--mem-limit MEM_LIMIT] [--pids-limit PIDS_LIMIT]
                          [--network NETWORK]
                          [script_path]
```

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `script_path` | Positional | *Optional* | Path to target shell script (auto-discovers if omitted) |
| `-j, --jobs` | Integer | `min(2, size)` | Number of concurrent container jobs |
| `--matrix` | String | `debian:12-slim,ubuntu:22.04,ubuntu:24.04,alpine:3.20` | Comma-separated list of Docker images |
| `--timeout` | Integer | `60` | Hard timeout per container in seconds |
| `--format` | Choice | `table` | Output format: `table`, `markdown`, or `json` |
| `--shell` | Choice | `posix` | Execution mode: `posix` (default), `shebang`, or `auto` |
| `--mem-limit` | String | `256m` | Memory limit per container (e.g. `256m`, `512m`) |
| `--pids-limit`| Integer | `128` | Maximum number of processes per container |
| `--network` | Choice | `bridge` | Container network mode: `bridge` or `none` |
| `--version` | Flag | - | Show version number |
| `-h, --help` | Flag | - | Show argument help |

### Shell Execution Modes (`--shell`)

- **`posix`** (default): Strictly executes with `/bin/sh`, ignoring any script shebang to verify portability against minimal POSIX environments (including Alpine BusyBox).
- **`shebang`**: Strictly honors the interpreter specified in the script's shebang (`#!/bin/sh`, `#!/bin/bash`, `#!/usr/bin/sh`, `#!/usr/bin/bash`, `#!/usr/bin/env sh`, `#!/usr/bin/env bash`). Fails immediately if shebang is missing, malformed, or unsupported.
- **`auto`**: Honors recognized shebangs if present; safely falls back to `/bin/sh` if no shebang is present.

### Exit Code Convention
- **`0`**: All tested scripts and distributions passed (`PASS`).
- **`1`**: At least one distribution failed (`FAIL`), timed out (`TIMED_OUT`), or errored (`ERROR`).

---

## 🐶 Dogfooding

OpsScript Gate is actively used in [`Mresyzz/linux-dev-bootstrap`](https://github.com/Mresyzz/linux-dev-bootstrap) to validate `install.sh` across the default Debian, Ubuntu, and Alpine matrix in GitHub Actions.

See the downstream workflow: [`.github/workflows/test.yml`](https://github.com/Mresyzz/linux-dev-bootstrap/blob/main/.github/workflows/test.yml).

---

## 🧪 Development & Testing

```bash
# Clone repository
git clone https://github.com/Mresyzz/opsscript-gate.git
cd opsscript-gate

# Install in editable mode with test dependencies
pip install -e .[test]

# Run unit tests (Mocked, no Docker daemon required)
pytest -v -m "not integration"

# Run integration tests (Requires local Docker daemon)
pytest -v
```

---

## 📄 License

OpsScript Gate is licensed under the [MIT License](LICENSE).
