# OpsScript Gate Roadmap

This roadmap tracks features being considered for future releases.

> **Note:** Features listed below are planned or under consideration; they are not implemented in current releases.

---

## Planned Features

### 1. Execution Modes (`--shell`)
- [x] **Shebang-aware execution (`--shell shebang | auto`)**: Implemented in v0.2.0. Parses and honors recognized shebang forms (`sh`, `bash`) across distributions using fixed trusted container commands.
- [x] **Explicit POSIX mode (`--shell posix`)**: Implemented in v0.2.0. Retains `/bin/sh` baseline across all containers to verify strict POSIX portability.

### 2. Resource Constraints
- [ ] **Memory limits (`--mem-limit`)**: Planned. Constrain container memory usage for scripts under test.
- [ ] **PID limits (`--pids-limit`)**: Under consideration. Guard against fork bombs within the timeout window.

### 3. Network Isolation
- [ ] **Offline execution (`--network none`)**: Planned. Run verification without network access for scripts that should not require network connectivity.

### 4. Matrix & Distribution Presets
- [ ] **Additional distributions**: Under evaluation (e.g. Rocky Linux, Fedora).
- [ ] **Parallel container execution**: Under consideration to reduce execution time on multi-core runners.

### 5. Tooling & CI Integration
- [ ] **GitHub Workflow Problem Matchers**: Under consideration. Provide inline annotations on pull request diffs for failure lines.

---

## Suggestions & Feedback

To propose an addition or share feedback on priorities, open a [Feature Request](https://github.com/Mresyzz/opsscript-gate/issues/new?template=feature_request.yml) on GitHub.
