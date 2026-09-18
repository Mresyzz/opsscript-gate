# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-09-19

### Fixed
- Strip complete ANSI CSI and OSC escape sequences from diagnostic text instead of leaving escape-sequence residue.
- Ensure diagnostic `max_length` includes the trailing ellipsis when truncation occurs.
- Add regression coverage for ANSI sanitization and truncation edge cases.

---

## [0.2.0] - 2026-09-18

### Added
- Explicit shell execution modes (`--shell posix|shebang|auto`) in CLI and GitHub Action.
  - `posix` (default): Strictly executes with `/bin/sh`, ignoring any script shebang to verify portability against minimal POSIX environments.
  - `shebang`: Strictly honors recognized shebang interpreters (`sh`, `bash`, `/usr/bin/env`). Fails immediately with clear diagnostics if missing, malformed, or unsupported.
  - `auto`: Uses recognized shebang when present; safely falls back to `/bin/sh` if no shebang is present; rejects unsupported/malformed shebangs without silent fallback.
- Exact interpreter-path preservation using fixed trusted container command constants (`SUPPORTED_SHEBANG_COMMANDS`), preventing `$PATH` resolution from masking missing paths like `/usr/bin/bash`.
- Hardened GitHub Action input passing via step-level environment variables to eliminate shell injection risks.
- Dedicated Docker integration test job in GitHub Actions workflow verifying real container behaviors (including bash missing on Alpine 3.20).
- Sanitized shebang error diagnostics against control character injection and multiline pollution.

---

## [0.1.2] - 2026-09-18

### Added
- Configured PyPI Trusted Publishing via GitHub Actions OIDC (`pypa/gh-action-pypi-publish`).
- Added full PyPI package metadata, classifiers, and project URLs to `pyproject.toml`.
- Ensured absolute asset URLs in `README.md` for seamless PyPI rendering.

---

## [0.1.1] - 2026-09-18

### Added
- Created `examples/` directory showcasing basic setup, Alpine package manager incompatibility, and interactive hang prevention.
- Added GitHub Issue templates for bug reports, feature requests, and distribution support requests.
- Added `CONTRIBUTING.md`, `SECURITY.md`, and `ROADMAP.md`.
- Enforced `security_opt=["no-new-privileges:true"]` on all container executions.

### Fixed
- Upgraded GitHub Actions dependencies to `actions/checkout@v7` and `actions/setup-python@v7` (Node 24 runtime).
- Fixed secret referencing syntax in release workflow to ensure reliable binary asset uploads.

---

## [0.1.0] - 2026-09-18

### Added
- Initial MVP release of `opsscript-gate`.
- CLI entrypoint (`opsscript-gate run <script_path>`).
- Unprivileged container isolation engine supporting `debian:12-slim`, `ubuntu:22.04`, `ubuntu:24.04`, and `alpine:3.20`.
- Safe read-only script mounting (`:ro`).
- Hard per-container timeout with forced `SIGKILL` and cleanup.
- Stdin disconnection (`</dev/null`) and non-interactive environment enforcement.
- Windows CRLF line-ending normalization defense.
- Unified ASCII table, GitHub Actions Step Summary Markdown, and JSON reporting formats.
- Composite GitHub Action published to Marketplace.
- Unit and integration test suite.
