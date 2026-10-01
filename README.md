# OpsScript Gate — shell script compatibility testing

[简体中文](README.zh-CN.md) · [Configuration](docs/configuration.md) · [Troubleshooting](docs/troubleshooting.md) · [Self-hosted model installer guide](docs/gpt-oss.md)

> ShellCheck analyzes shell syntax. OpsScript Gate executes scripts in Linux containers.

[![CI](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml)
[![Demo](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml)
[![PyPI](https://img.shields.io/pypi/v/opsscript-gate)](https://pypi.org/project/opsscript-gate/)
[![Python Versions](https://img.shields.io/pypi/pyversions/opsscript-gate)](https://pypi.org/project/opsscript-gate/)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-OpsScript%20Gate-blue?logo=github&color=2088FF)](https://github.com/marketplace/actions/opsscript-gate)
[![Release](https://img.shields.io/github/v/release/Mresyzz/opsscript-gate?color=green)](https://github.com/Mresyzz/opsscript-gate/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Supported Distros](https://img.shields.io/badge/matrix-Debian%20%7C%20Ubuntu%20%7C%20Alpine-orange.svg)](#default-test-matrix)

**OpsScript Gate** is a runtime compatibility checker for Linux shell scripts. It executes scripts inside unprivileged Debian, Ubuntu, and Alpine containers, catching environment-specific failures, missing interpreters, and package-manager assumptions that static analysis cannot detect.

It is designed for shell testing, portable shell validation, Bash/POSIX compatibility checks, and cross-distro CI where syntax-only tooling is not enough.

If your repository contains an installer, bootstrap script, or shell entrypoint, the fastest path is to
open the [InstallReady scanner](https://mresyzz.github.io/InstallReady/), enter `owner/repository`, and
choose **Add workflow on GitHub**. It generates a reviewable workflow without an account, API key, or
service signup. You can also copy the maintained [zero-configuration workflow](.github/workflow-templates/opsscript-gate.yml).

Try the browser scanner: [InstallReady](https://mresyzz.github.io/InstallReady/?repo=Mresyzz%2Fopsscript-gate) checks this repository without executing code or requiring a login.

---

## Current release: v0.6.3

The current release includes a project config file, a dry-run plan, presets, exclusions,
saved reports, and changed-script selection for pull requests. The project controls
were introduced in v0.5.0; projects on v0.4.1 and earlier do not include them.

```bash
opsscript-gate init
opsscript-gate doctor
opsscript-gate run --dry-run
opsscript-gate run --format json --output reports/compatibility.json
```

`init` creates `.opsscript-gate.json` and a GitHub Actions workflow without replacing
existing files. Review its exclusions (`tests/*`, `examples/*`) and offline network
default before running. No Docker is required for `init` or `--dry-run`.
Use `opsscript-gate doctor` to check Python and Docker before a real run.

Useful for standalone installers, container entrypoints and release scripts that
must work on both GNU/Linux and Alpine/BusyBox. Each script runs independently;
repository files, sibling scripts and project dependencies are **not** mounted.
See [configuration and migration](docs/configuration.md) and
[why a shell script works on Ubuntu but fails on Alpine](docs/troubleshooting.md).

## Quickstart

### In GitHub Actions

Add this workflow to `.github/workflows/shell-compat.yml`:

The repository includes a maintained [workflow template](.github/workflow-templates/opsscript-gate.yml).
For a one-click setup in another public repository, use the InstallReady scanner above; it opens GitHub's
workflow editor with the generated file ready to review.

You can copy the maintained example from [`examples/github-actions/workflow.yml`](examples/github-actions/workflow.yml)
and change the `script-path`, or use the minimal workflow below.

```yaml
name: Shell Compatibility Gate
on: [pull_request, push]

jobs:
  compat:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: Mresyzz/opsscript-gate@v0.6.3
```

This zero-configuration form discovers shell scripts in the repository. Use
`opsscript-gate run --dry-run` to inspect the selection, or set `script-path` when the
repository has a single installer. For self-hosted model installers, see the
[installer guide](docs/gpt-oss.md).

Or test a specific script with custom execution modes:

```yaml
      - uses: Mresyzz/opsscript-gate@v0.6.3
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

### Test only scripts changed in a pull request

Fetch the comparison revision and pass the pull request base SHA to avoid running
unrelated scripts:

```yaml
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
          fetch-depth: 0
      - uses: Mresyzz/opsscript-gate@v0.6.3
        with:
          changed-since: ${{ github.event.pull_request.base.sha }}
          preset: minimal
```

If the change does not include a shell script, the check passes without starting a
container. The same selection can be previewed locally with
`opsscript-gate run --changed-since origin/main --dry-run`.

### Example: package-manager mismatch

Create `install.sh`:

```sh
#!/bin/sh
set -e
apt-get --version
```

Then run:

```bash
opsscript-gate run ./install.sh
```

A typical result across the default matrix looks like this:

```text
Debian 12        PASS
Ubuntu 22.04     PASS
Ubuntu 24.04     PASS
Alpine 3.20      FAIL

apt-get: not found
```

The script is valid shell, but it assumes a command that is not present in Alpine.

---

## CI output

The action reports failures in two places:

### GitHub annotations
Failures include the script path, line number, distribution, and a short diagnostic:

```text
::error file=scripts/setup.sh,line=4,title=OpsScript Gate: [alpine:3.20] command not found: apt-get::command not found: apt-get — Alpine normally uses apk instead of apt-get.
```

### Step summary
The action also writes a markdown matrix to `$GITHUB_STEP_SUMMARY`:

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
<summary><b>Markdown result</b></summary>
...
</details>
```

### SARIF for Code Scanning

Use `sarif` when the result should appear in GitHub Code Scanning or another
SARIF-compatible viewer. Upload it explicitly with the official upload action:

```yaml
- uses: Mresyzz/opsscript-gate@v0.6.3
  with:
    script-path: scripts/install.sh
    format: sarif
    output: reports/opsscript-gate.sarif

- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: reports/opsscript-gate.sarif
```

Each runtime failure becomes a location-aware result with the distribution,
exit code, command, and diagnostic line. A passing matrix produces a valid SARIF
file with no findings.

---

## Example: runtime behavior that static analysis misses

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

**Why it failed:** Alpine uses `apk`, not `apt-get`. The report includes the missing command and its line number.

---

## Scope compared with other checks

### OpsScript Gate compared with ShellCheck and a custom CI matrix

| Capability | OpsScript Gate | ShellCheck | Handwritten CI Matrix |
| :--- | :---: | :---: | :---: |
| **Runtime execution** | **Yes** | No (Static AST only) | Yes |
| **Real distro environments** | **Yes (Debian, Ubuntu, Alpine)** | No | Yes |
| **Preconfigured defaults** | **Yes** | Yes | Requires custom workflow configuration |
| **Restricted container defaults** | **Built-in (`ro`, `cap_drop`, resource limits)** | N/A | User-defined |
| **Anti-hang stdin protection** | **Built-in (`</dev/null`, noninteractive)** | No | User-defined |
| **Line-Level Annotations & Hints** | **Built-in** | Static warnings | User-defined |
| **Parallel Matrix Execution** | **Built-in (`--jobs`)** | N/A | Manual matrix config |

ShellCheck checks shell syntax and common mistakes. OpsScript Gate runs the script in
real distributions. A custom CI matrix can do the same job, but each repository must
maintain its own images, mounts, timeouts, and report handling.

---

## Security boundaries and container isolation

OpsScript Gate is a runtime compatibility testing tool, **not a security sandbox for hostile or fully untrusted code**. Containers still share the host kernel, so target scripts should be treated accordingly.

<details>
<summary><strong>View security boundaries and runtime hardening details</strong></summary>

The runner uses restricted container defaults:

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
   - Injects `DEBIAN_FRONTEND=noninteractive` and `CI=true`. Interactive prompts (`read -p`) fail instead of hanging CI runners.
5. **Hard Timeout & Container Cleanup**:
   - Enforces configurable timeout (default: 60s). Timed-out containers are sent `SIGKILL` and marked `TIMED_OUT`.
   - Container removal is attempted from a `finally` block in normal, failure, and timeout execution paths.
6. **Bounded Output & Memory Protection**:
   - Captures container logs using a rolling byte buffer capped at 256 KiB (`MAX_CAPTURED_LOG_BYTES`) and a 500-line tail limit (`MAX_LOG_TAIL_LINES`) to reduce memory-exhaustion risk from runaway output.
7. **Untrusted Log Neutralization & Terminal Defense**:
   - Neutralizes line-leading workflow commands (`[container] ::`) to prevent forged GitHub Actions annotations in CI runners.
   - Strips ANSI escape sequences and dangerous C0 control characters, and normalizes carriage returns (`\r`) to defeat terminal line-overwrite spoofing.
   - Employs context-sensitive escaping (`escape_inline_code`, `escape_markdown_text`, `escape_markdown_table_cell`, `escape_html_text`, `format_safe_code_fence`) to protect Step Summary output contexts.
8. **Command Injection Defense**:
   - OpsScript Gate's own annotations (`::error`) apply strict percent-encoding for workflow-command fields and message bodies.
9. **Bounded Streaming CRLF & Shebang Defense**:
   - Stream-normalizes CRLF in 64 KiB chunks and bounds shebang parsing to 4096 bytes without whole-file memory allocation.
   - Pre-normalizes scripts once before parallel matrix runs, sharing a read-only prepared path across worker threads.

For the complete supported-version policy and vulnerability reporting guidance, see [SECURITY.md](SECURITY.md).

</details>

### When NOT to use OpsScript Gate

OpsScript Gate is intentionally focused on Linux shell runtime compatibility. It is not designed for:

- executing hostile or fully untrusted third-party scripts
- kernel-level or privileged behavior testing
- replacing full integration or end-to-end test suites
- validating macOS or Windows behavior
- proving that a script is secure

Use it when you want to know whether a shell script actually runs across the supported Linux distributions.

---

## Default test matrix

| Image | Distribution | Focus |
| :--- | :--- | :--- |
| `debian:12-slim` | Debian 12 (Bookworm) | Minimal glibc + APT base |
| `ubuntu:22.04` | Ubuntu 22.04 LTS (Jammy) | Enterprise long-term support baseline |
| `ubuntu:24.04` | Ubuntu 24.04 LTS (Noble) | Modern glibc, updated coreutils & defaults |
| `alpine:3.20` | Alpine Linux 3.20 | Minimal musl libc + BusyBox /bin/sh environment |

Customize the matrix at any time via `--matrix` or Action input `matrix`.

---

## CLI reference

Check local prerequisites before starting containers:

```text
opsscript-gate doctor [--format table|json]
```

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
| `--format` | Choice | `table` | Output format: `table`, `markdown`, `json`, or `sarif` |
| `--shell` | Choice | `posix` | Execution mode: `posix` (default), `shebang`, or `auto` |
| `--mem-limit` | String | `256m` | Memory limit per container (e.g. `256m`, `512m`) |
| `--pids-limit`| Integer | `128` | Maximum number of processes per container |
| `--network` | Choice | `bridge` | Container network mode: `bridge` or `none` |
| `--changed-since` | Git revision | - | Test shell scripts changed between this revision and `HEAD` |
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

### v0.5.0 project controls

| Option | Purpose |
| :--- | :--- |
| `init` | Generate configuration and a GitHub workflow without overwriting files |
| `--dry-run` | Preview selected scripts, images and total executions without Docker |
| `--config PATH` | Load a specific JSON configuration file |
| `--preset minimal` | Debian + Alpine (two container runs per script) |
| `--preset ubuntu` | Ubuntu 22.04 + 24.04 |
| `--exclude 'tests/*'` | Exclude a repository-relative glob; repeatable |
| `--max-scripts 50` | Raise the default discovery limit of 20; overflow is an error |
| `--output report.json` | Save the selected output format, including failed test reports |

Explicit CLI options override project settings. Explicit script paths bypass discovery
and its exclusions. See [complete configuration semantics](docs/configuration.md).

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

## Feedback

Please report compatibility cases, bugs, and pull requests in the issue tracker.

---

## 📄 License

OpsScript Gate is licensed under the [MIT License](LICENSE).
