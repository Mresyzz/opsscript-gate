# OpsScript Gate Roadmap

This document outlines planned capabilities for OpsScript Gate. We prioritize pragmatism, minimal overhead, and uncompromised container security.

> **Note:** Features listed below are planned and under evaluation, not yet implemented in the current v0.1.x release.

---

## 🧭 Planned Milestones

### 1. Execution Modes (`--shell`)
- [ ] **Shebang-aware mode (`--shell shebang | auto`)**: Parse and honor `#!/usr/bin/env bash` or `#!/bin/bash` in distributions where Bash is present, while still maintaining strict unprivileged execution.
- [ ] **Strict POSIX mode (`--shell posix`)**: Keep the current baseline of `/bin/sh` across all containers to verify baseline portability.

### 2. Fine-grained Resource Constraints
- [ ] **Configurable memory limits**: Add `--mem-limit` (defaulting to e.g. `512m`) to prevent rogue runaway scripts from exhausting host RAM.
- [ ] **CPU and PID limits**: Add `--pids-limit` (e.g. 128) and `--cpus` to guard against fork bombs within the hard timeout window.

### 3. Network Isolation Modes
- [ ] **Offline sandboxing (`--network none`)**: Run verification completely offline for purely local logical ops scripts.
- [ ] **Standard bridge (`--network bridge`)**: Keep as default when network access is required (e.g. package installation tests).

### 4. Matrix & Distribution Presets
- [ ] **Enterprise Linux presets**: Support standard images for Enterprise Linux (Rocky Linux / AlmaLinux / Fedora).
- [ ] **Parallel container execution**: Concurrently execute distribution matrices to reduce CI run times on multi-core runners.

### 5. Ecosystem & Linter Integration
- [ ] **ShellCheck complementary stage**: Optional pre-flight linting pass to combine static AST analysis with container runtime verification.
- [ ] **GitHub Workflow Problem Matchers**: Automatic inline annotations on pull request diffs for failed line numbers.

---

## 💡 Suggesting Roadmap Items

To propose an addition or vote on roadmap priority, please open a [Feature Request](https://github.com/Mresyzz/opsscript-gate/issues/new?template=feature_request.yml) on GitHub.
