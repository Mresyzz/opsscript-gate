# opsscript-gate

A lightweight, non-privileged containerized pre-release verification tool and GitHub Action for Linux maintenance Shell scripts.

## Purpose

`opsscript-gate` runs target shell scripts inside minimal, isolated containers across multiple distributions (Debian 12, Ubuntu 22.04, Ubuntu 24.04, Alpine 3.20). It helps detect missing commands, syntax/shebang issues, unhandled errors, interactive hangs, and cross-distro incompatibilities BEFORE releasing.

## Safety & Scope

*   **NO Privileged Containers**: Containers run strictly in unprivileged mode.
*   **Deterministic Timeouts & Process Cleanup**: Strict timeouts are enforced.
*   **Prevent Interactive Hangs**: `DEBIAN_FRONTEND=noninteractive` and disconnected `stdin` prevent hanging CI.

## Quickstart

```bash
pip install .
opsscript-gate path/to/script.sh
```
