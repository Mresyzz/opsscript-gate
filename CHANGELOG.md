# Changelog

## [0.9.1] - 2026-10-03

### Fixed
- Normalized discovery exclusions so top-level paths match with or without `./`.
- Made SARIF output conform to the 2.1.0 result schema.
- Failed closed when Docker omitted an exit code and separated package setup errors from script failures.
- Validated project configuration in `doctor` and handled UTF-8 BOM scripts.
- Distinguished Docker wait API errors from genuine execution timeouts.

## [0.9.0] - 2026-10-03

### Added
- Added `--repeat` and Action/config `repeat` support to detect flaky runtime behavior per distribution.
- Added attempt counts and `FLAKY` status to JSON, Markdown, SARIF, terminal, and GitHub Step Summary reports.

### Fixed
- Bounded project configuration reads to prevent oversized configuration files from consuming unbounded memory.
- Prefer Docker's blocking wait API over repeated synchronous container reloads, while retaining a bounded compatibility fallback.
- Removed duplicated CLI execution error handling and the unused `asdict` import.

## [0.8.3] - 2026-10-02

- Corrected the PyPI homepage and demo links to point to the OpsScript Gate Pages site.
- Refreshed all generated examples and release metadata to v0.8.3.

## [0.8.2] - 2026-10-02

### Fixed
- Disabled both APT post-invoke hook variants used by current base images during ephemeral package setup.

## [0.8.1] - 2026-10-02

### Fixed
- Prevented Debian and Ubuntu image cleanup hooks from turning optional package setup into a false compatibility failure.
- Kept package installation and target script failures fail-closed while making ephemeral cache cleanup best-effort.

## [0.8.0] - 2026-10-02

### Added
- Added opt-in `packages` setup for installing validated package names with
  `apt-get` or `apk` before each container run; package setup requires bridge
  networking and leaves existing offline runs unchanged.

## [0.7.0] - 2026-10-01

### Added
- Added `opsscript-gate doctor` to diagnose Python and Docker prerequisites before a local run.
- Added SARIF 2.1.0 output for location-aware GitHub Code Scanning integration.

### Changed
- Expanded package and Marketplace keywords for shell installers, ShellCheck users, portability, and BusyBox.
- Clarified the Action description around shell installer runtime compatibility.

## [0.6.2] - 2026-10-01

### Changed
- Updated the published README and Action examples to the current release tag.
- Added the InstallReady browser scanner to the package homepage and project links.
- Made the starter workflow follow each repository's default branch.

## [0.6.1] - 2026-10-01

### Added
- Added a zero-configuration GitHub workflow starter that runs only when shell files change.
- Added a copyable compatibility report artifact to the starter workflow.
- Added citation metadata and clearer PyPI keywords for installer and bootstrap use cases.

### Changed
- Marked the project Beta now that the default matrix, safety controls, reports, presets, and changed-script mode are released.
- Updated the roadmap to show the v0.5 and v0.6 controls as delivered.

## [0.6.0] - 2026-09-30

### Added
- Added `--changed-since` and the matching Action input to test only shell scripts changed since a Git revision.
- Changed-script selection uses the existing discovery safety checks and passes when a change contains no shell scripts.

## [0.5.1] - 2026-09-30

### Changed
- Published the current README and examples with the v0.5.1 Action tag.
- Updated package and Action metadata to describe the supported container matrix and runtime compatibility check.

## [0.5.0] - 2026-09-24

### Added
- Added `opsscript-gate init` to create a config file and GitHub workflow without replacing existing files.
- Added `.opsscript-gate.json` with CLI and Action overrides.
- Added `--dry-run`, `minimal` and `ubuntu` presets, exclusion globs, and `--output` reports.
- Added configuration, Chinese quickstart, and Ubuntu/Alpine troubleshooting documentation.

### Fixed
- Discovery stops at the first candidate beyond the configured limit instead of silently ignoring files.
- Discovery skips symlinks and non-files and checks shebangs without prefix matches.
- CLI validates limits and network modes before execution.
- Empty Action inputs no longer override project configuration.

### Migration
- Repositories with more than 20 discovered scripts must exclude unwanted scripts or raise `max_scripts`.
- Auto-discovery no longer follows file symlinks; explicit script paths remain supported.
- Default settings without a configuration file remain compatible with v0.4.1 and earlier.
- Generated workflows use the v0.5.0 release tag.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-09-19

### Fixed & Hardened
- Bounded container log capture with a 256 KiB rolling buffer and 500-line tail.
- Neutralized untrusted container logs beginning with `::` before they reach GitHub Actions.
- **Terminal ANSI and control character sanitization**: Strips ANSI escape sequences (CSI, OSC, 2-byte escapes), removes dangerous C0 control characters and DEL, and normalizes CRLF and standalone carriage returns (`\r`) to defeat terminal line overwrite and status spoofing, while preserving printable Unicode.
- **Context-sensitive Markdown and HTML injection defense**: Implemented dedicated escaping (`escape_inline_code`, `escape_markdown_text`, `escape_markdown_table_cell`, `escape_html_text`, `format_safe_code_fence`) to prevent table cell tearing, HTML container breakout (`</details>`), premature code fence closure, and structural Markdown injection from runtime-derived values.
- **Bounded streaming script preparation**: Stream-normalizes CRLF in bounded 64 KiB chunks (`SCRIPT_READ_CHUNK_SIZE`), properly handling boundary-split CRLF while preserving lone CR bytes without whole-file memory allocation. Bounded shebang parsing to 4096 bytes (`MAX_SHEBANG_BYTES`).
- **Parallel matrix script preparation deduplication**: Pre-normalizes scripts once before parallel matrix execution, sharing the prepared file read-only across worker threads and centralizing cleanup to eliminate file locking and race conditions on Windows.
- **Shebang evaluation refactoring**: Deduplicated shebang resolution across `shebang` and `auto` modes via `_resolve_shell_command`.
- **Regression test coverage**: Added extensive adversarial and edge-case tests covering oversized streams, boundary splits, workflow spoofing, Markdown injections, and error branches.

---

## [0.4.0] - 2026-09-19

### Added
- Line-level GitHub Actions annotations with script paths and line numbers.
- **Workflow command injection defense**: Strictly escapes parameters (`%`, `\r`, `\n`, `:`, `,`) and message bodies (`%`, `\r`, `\n`) to eliminate command injection from unclassified container logs.
- Distro-aware remediation hints for common mismatches, including:
  - Alpine package manager mismatches (`apt`/`apt-get` -> `apk`)
  - Debian/Ubuntu package manager mismatches (`apk` -> `apt-get`)
  - Alpine minimal missing Bash (`bash` -> consider POSIX sh or installing bash)
  - Missing network prerequisites (`curl`, `wget`)
  - Missing shebang interpreter paths.
- Updated the GitHub Actions Step Summary with a compatibility table and a Markdown result block.
- **Parallel matrix execution (`--jobs` / `jobs`)**: Concurrently runs container checks using `ThreadPoolExecutor` (defaults to `min(2, matrix_size)`), strictly preserving matrix output order and ensuring reliable container cleanup.
- **Hardened container resource limits**: Added `--mem-limit` (default: 256m) and `--pids-limit` (default: 128) flags and Action inputs to prevent runaway resource exhaustion.
- **Configurable network isolation (`--network`)**: Supports `--network bridge` (default) and `--network none` for offline script execution.
- **Zero-config repository script auto-discovery**: Running `opsscript-gate run` without arguments automatically discovers and validates shell scripts in the repository, ignoring directories like `.git`, `node_modules`, and `.venv`, capped at 20 scripts and 1 MB per file.
- **Multi-script test consolidation (`MultiScriptReport`)**: Supports aggregate reporting and Step Summary cards when multiple scripts are evaluated in a single run.

### Changed
- **Action initialization performance**: Removed redundant `pip install --upgrade pip` step in composite `action.yml` to minimize Action startup latency.
- **Flexible Action inputs**: Made `script-path` optional in `action.yml` (triggers auto-discovery if omitted); added inputs `jobs`, `mem-limit`, `pids-limit`, and `network`.

---

## [0.3.0] - 2026-09-19

### Added
- Structured runtime failure diagnostics: detect common "command not found" failures across Linux distributions (Alpine/BusyBox ash, Debian/Ubuntu dash, Bash, and missing interpreter paths).
- Missing-command classification requires exit code 127 and matching shell output.
- Additive `diagnostic` field in JSON report format (`SingleResult.to_dict()`) providing structured diagnostic information (backward-compatible for consumers tolerating additional fields).
- Enhanced terminal table formatting and GitHub Actions Step Summary showing clear failure causes in the summary overview.

---

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
- Ensured asset URLs in `README.md` render correctly on PyPI.

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
