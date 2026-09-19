# OpsScript Gate Roadmap

This roadmap tracks features delivered in recent releases and areas under consideration for future versions.

---

## Delivered in v0.4.0

- [x] **High-confidence Line-level GitHub Actions Annotations**: Emits safe `::error` annotations linking failure lines directly on pull request file diffs.
- [x] **Distro-aware Remediation Hints**: Conservative, testable hints for Alpine vs Debian package managers, missing bash interpreters, and core utilities.
- [x] **Interactive Compatibility Card & Copyable Summary**: Rich GitHub Actions Step Summary table with copy-pasteable Markdown snippets for PR/Issue triage.
- [x] **Parallel Matrix Execution (`--jobs` / `jobs`)**: Concurrent multi-container testing via `ThreadPoolExecutor` with strict matrix order preservation.
- [x] **Hardened Resource Limits**: Added `--mem-limit` (default: 256m) and `--pids-limit` (default: 128) container controls.
- [x] **Configurable Network Isolation (`--network none|bridge`)**: Run scripts offline when network access is not required.
- [x] **Zero-Config Script Auto-Discovery**: Automatically discovers candidate shell scripts in repository root when `script_path` is omitted.
- [x] **Composite Action Initialization Optimization**: Stripped redundant pip upgrade steps for rapid Action startup.

---

## Delivered in v0.2.0 - v0.3.0

- [x] **Structured Runtime Failure Diagnostics**: Detects "command not found" errors with exit code 127 validation (v0.3.0).
- [x] **Shebang-aware execution (`--shell shebang | auto`)**: Parses and honors recognized shebang forms (`sh`, `bash`) across distributions using fixed trusted container commands (v0.2.0).
- [x] **Explicit POSIX mode (`--shell posix`)**: Retains `/bin/sh` baseline across all containers to verify strict POSIX portability (v0.2.0).

---

## Planned for Future Releases (v0.5.0+)

### 1. Matrix & Distribution Presets
- [ ] **RPM-based distributions**: Evaluate support for Enterprise Linux baselines (e.g. Rocky Linux 9, AlmaLinux, Fedora).
- [ ] **Matrix presets**: Predefined profiles (e.g. `--preset minimal`, `--preset enterprise`, `--preset all`).

### 2. Performance & Caching
- [ ] **Docker image pre-pull & caching action**: Optional helper step to leverage GitHub Actions cache for test container base images.

### 3. Pre-run Setup Hooks
- [ ] **Script prerequisites hook**: Declarative environment setup (e.g. install custom apt packages before testing the target script).

---

## Suggestions & Feedback

To propose an addition or share feedback on priorities, open a [Feature Request](https://github.com/Mresyzz/opsscript-gate/issues/new?template=feature_request.yml) on GitHub.
