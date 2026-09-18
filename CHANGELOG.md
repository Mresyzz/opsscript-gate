# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
