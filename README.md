# OpsScript Gate

> **ShellCheck tells you if your script looks portable. OpsScript Gate checks if it actually runs there.**

[![CI](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml)
[![Demo](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-OpsScript%20Gate-blue?logo=github&color=2088FF)](https://github.com/marketplace/actions/opsscript-gate)
[![Release](https://img.shields.io/github/v/release/Mresyzz/opsscript-gate?color=green)](https://github.com/Mresyzz/opsscript-gate/releases)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Supported Distros](https://img.shields.io/badge/matrix-Debian%20%7C%20Ubuntu%20%7C%20Alpine-orange.svg)](#default-test-matrix)

**OpsScript Gate** is a drop-in runtime compatibility gate for Linux shell scripts. It executes your shell scripts inside isolated Debian, Ubuntu, and Alpine containers before release, catching environment-specific runtime failures that static analysis cannot detect.

<p align="center">
  <img src=".github/assets/social-preview.png" alt="OpsScript Gate Terminal Preview" width="800">
</p>

---

## ⚡ Quickstart (10 Seconds)

### In GitHub Actions

Add one step to your pull request workflow (`.github/workflows/gate.yml`):

```yaml
- name: Verify Shell Script Portability
  uses: Mresyzz/opsscript-gate@v0.1.1
  with:
    script-path: scripts/setup.sh
```

### In Local Terminal (CLI)

Requires Python 3.10+ and a local Docker engine:

```bash
# Install directly from GitHub
pip install git+https://github.com/Mresyzz/opsscript-gate.git

# Run compatibility gate against your script
opsscript-gate run ./scripts/setup.sh
```

---

## 🎯 30-Second Demo: What Static Linters Miss

Consider this innocent-looking deployment script:

```bash
#!/bin/sh
set -e
echo "Fetching package information..."
apt-get --version
```

Running `shellcheck` reports **0 errors, 0 warnings** because the syntax is perfectly valid POSIX shell.

However, when verified with **OpsScript Gate**:

```text
+--------------------+----------+-----------+------------+----------------------------------------------------+
| Distro             | Status   | Exit Code | Duration   | Details                                            |
+--------------------+----------+-----------+------------+----------------------------------------------------+
| debian:12-slim     | PASS     | 0         | 1.15s      | OK                                                 |
| ubuntu:22.04       | PASS     | 0         | 1.08s      | OK                                                 |
| ubuntu:24.04       | PASS     | 0         | 1.12s      | OK                                                 |
| alpine:3.20        | FAIL     | 127       | 0.45s      | Script failed with non-zero exit code: 127         |
+--------------------+----------+-----------+------------+----------------------------------------------------+
Total duration: 3.80s | Result: FAILED

============================================================
Failed Distributions - Output Snippets (last 15 lines):
============================================================

--- [alpine:3.20] (FAIL) ---
/tmp/target_script.sh: line 4: apt-get: not found
```

**Why it failed:** Alpine Linux is musl/BusyBox-based and uses `apk`, not `apt-get`. OpsScript Gate detects the missing utility (`exit code 127`) in milliseconds before the script breaks production.

---

## 💡 Why OpsScript Gate?

### OpsScript Gate vs ShellCheck vs Custom CI Matrix

| Capability | OpsScript Gate | ShellCheck | Handwritten CI Matrix |
| :--- | :---: | :---: | :---: |
| **Runtime execution** | **Yes** | No (Static AST only) | Yes |
| **Real distro environments** | **Yes (Debian, Ubuntu, Alpine)** | No | Yes |
| **Zero-boilerplate defaults** | **Pre-packaged defaults** | Yes | Requires custom workflow configuration |
| **Safe container defaults** | **Built-in (`ro`, `cap_drop`, `kill`)** | N/A | User-defined |
| **Anti-hang stdin protection** | **Built-in (`</dev/null`, noninteractive)** | No | User-defined |
| **Unified summary & diagnostics** | **Built-in (ASCII + Step Summary)** | Static warnings | User-defined |

- **ShellCheck** is indispensable for static analysis (syntax, quoting, SC warnings). OpsScript Gate complements it by testing actual execution behavior in real distributions.
- **Handwritten CI Matrix** requires maintaining complex Docker configurations, volume mounts, timeout guards, and log parsers across every project. OpsScript Gate packages all of this into a single, reliable gate.

---

## 🛡️ Security & Isolation Boundaries

When executing arbitrary maintenance scripts, containment is non-negotiable:

1. **Unprivileged by Design**:
   - Containers run with `privileged=False`.
   - All Linux capabilities are dropped: `cap_drop=["ALL"]`.
   - Privilege escalation is strictly disabled: `security_opt=["no-new-privileges:true"]`.
2. **Read-Only Target Mount**:
   - The tested script is mounted strictly as a read-only volume (`:ro`) at `/tmp/target_script.sh`.
   - OpsScript Gate does not mount additional host filesystem paths into the test container.
3. **Anti-Hang Deadlock Defense**:
   - Disables TTY and stdin (`stdin_open=False`, `tty=False`).
   - Redirects execution: `/bin/sh -c "/bin/sh /tmp/target_script.sh </dev/null"`.
   - Injects `DEBIAN_FRONTEND=noninteractive` and `CI=true`.
   - Any script accidentally prompting for user input (`read -p`) fails immediately instead of blocking the CI pipeline for hours.
4. **Hard Timeout & Zero-Zombie Cleanup**:
   - Enforces a strict timeout (default: 60s). Timed-out containers are sent `SIGKILL` and marked `TIMED_OUT`.
   - Cleanup is attempted in a `finally` block on all normal Python execution paths, including test failures and timeouts.
5. **Windows CRLF Defense**:
   - Automatically detects and normalizes carriage returns (`\r\n` -> `\n`) before container execution, preventing false `\r: command not found` errors.
6. **POSIX-oriented `/bin/sh` Baseline**:
   - Containers invoke `/bin/sh` directly, catching undeclared Bashism syntax (e.g. bash arrays, `[[ ... ]]`) that break in lightweight Alpine environments.

---

## 🌐 Default Test Matrix

| Image | Distribution | Focus |
| :--- | :--- | :--- |
| `debian:12-slim` | Debian 12 (Bookworm) | Minimal glibc + APT base |
| `ubuntu:22.04` | Ubuntu 22.04 LTS (Jammy) | Enterprise long-term support baseline |
| `ubuntu:24.04` | Ubuntu 24.04 LTS (Noble) | Modern glibc, updated coreutils & defaults |
| `alpine:3.20` | Alpine Linux 3.20 | Minimal musl libc + BusyBox (strict POSIX test) |

You can customize the matrix at any time via `--matrix` or Action input `matrix`.

---

## 📖 CLI Reference

```text
usage: opsscript-gate run [-h] [--matrix MATRIX] [--timeout TIMEOUT]
                          [--format {table,markdown,json}]
                          script_path
```

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `script_path` | Positional | *Required* | Path to target shell script |
| `--matrix` | String | `debian:12-slim,ubuntu:22.04,ubuntu:24.04,alpine:3.20` | Comma-separated list of Docker images |
| `--timeout` | Integer | `60` | Hard timeout per container in seconds |
| `--format` | Choice | `table` | Output format: `table`, `markdown`, or `json` |
| `--version` | Flag | - | Show version number |
| `-h, --help` | Flag | - | Show argument help |

### Exit Code Convention
- **`0`**: All distributions passed (`PASS`).
- **`1`**: At least one distribution failed (`FAIL`), timed out (`TIMED_OUT`), or errored (`ERROR`).

---

## 📁 Examples

Check out the [examples/](examples/) directory for self-contained, runnable scenarios:

- [`examples/basic/`](examples/basic/): A clean POSIX script that passes across all distributions.
- [`examples/alpine-incompatibility/`](examples/alpine-incompatibility/): Demonstrates catching implicit Debian/Ubuntu dependencies (e.g. `apt-get`).
- [`examples/interactive-hang/`](examples/interactive-hang/): Demonstrates how unhandled `read` prompts fail immediately instead of hanging.
- [`examples/github-actions/`](examples/github-actions/): Ready-to-copy production pull request workflow.

---

## 🧪 Local Development & Testing

The test suite uses full Docker SDK mocking to ensure lightning-fast unit tests without needing a local daemon:

```bash
# Clone and install with test dependencies
git clone https://github.com/Mresyzz/opsscript-gate.git
cd opsscript-gate
pip install -e .[test]

# Run unit tests (Mocked, runs in < 0.5s)
pytest -v -m "not integration"

# Run integration tests (Requires Docker daemon)
pytest -v
```

---

## 🗺️ Roadmap

See [ROADMAP.md](ROADMAP.md) for planned capabilities, including:
- Shebang-aware execution modes (`--shell auto|posix|shebang`)
- Container resource limits (`--mem-limit`, `--pids-limit`)
- Configurable network isolation (`--network none|bridge`)
- Parallel matrix execution

---

## 🤝 Community & Security

- **Contributing**: Please review [CONTRIBUTING.md](CONTRIBUTING.md) for pull request guidelines and security red lines.
- **Security Policy**: Read [SECURITY.md](SECURITY.md) to report vulnerabilities responsibly.
- **Changelog**: See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## 📄 License

OpsScript Gate is licensed under the [MIT License](LICENSE).
