# Test self-hosted model installer scripts

OpsScript Gate fits the installation and release layer of a self-hosted model project. It
executes shell scripts in Debian, Ubuntu, and Alpine containers to catch distribution
differences, missing commands, package-manager assumptions, and interactive hangs.

This guide uses [OpenAI's gpt-oss open-weight models](https://openai.com/index/introducing-gpt-oss/)
as a concrete example. The checks cover installer scripts, startup scripts, and container
entrypoints. They do **not** test GPU drivers, CUDA/ROCm, model weights, inference speed,
output quality, or the memory requirements of a particular machine. Keeping this boundary
explicit prevents a script-compatibility check from being mistaken for a complete model
deployment test.

## Check changed scripts in pull requests

Assume the repository contains `scripts/bootstrap-gpt-oss.sh` or another shell installer:

```yaml
name: Model installer compatibility

on:
  pull_request:

permissions:
  contents: read

jobs:
  shell-runtime:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
          persist-credentials: false

      - uses: Mresyzz/opsscript-gate@v0.6.3
        with:
          changed-since: ${{ github.event.pull_request.base.sha }}
          preset: minimal
          shell: auto
          network: none
```

`changed-since` selects only shell files changed in the commit range. Documentation,
Python, model configuration, and frontend changes do not start containers. If no shell
file changed, the check passes without doing container work.

If the installer must download packages or model files, change `network` to `bridge` and
keep downloads in a dedicated test script. Once network access is enabled, upstream
mirrors and package indexes can affect repeatability.

## Preview and run locally

Confirm the selection before starting Docker:

```bash
pip install opsscript-gate
opsscript-gate run --changed-since origin/main --preset minimal --shell auto --dry-run
opsscript-gate run scripts/bootstrap-gpt-oss.sh --preset minimal --shell auto --network none
```

If an installer depends on other repository files, an explicit `script-path` still checks
only that script; dependencies are not mounted into the container. Put the required logic
behind a standalone test entrypoint, or use the project's integration tests for file-level
collaboration and use OpsScript Gate for the cross-distribution runtime layer.

## What to inspect when a check fails

- `apt-get` is missing on Alpine: choose `apk` for that distribution, or detect it and
  return a clear message.
- `bash` is missing: declare `#!/usr/bin/env bash` for Bash syntax, use `shell: auto`, and
  confirm that the selected test image includes Bash.
- The script waits for input: remove interactive prompts or return a clear non-interactive
  error.
- A download fails: separate script failures from network or package-index instability;
  use `network: bridge` only when needed and pin versions with checksums.

Model loading, GPU drivers, and inference quality belong in the project's hardware
integration tests. OpsScript Gate makes the installer and startup scripts pass a small,
repeatable shell-runtime check before those expensive tests run.
