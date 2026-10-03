# How to debug `command not found` in Debian, Ubuntu, and Alpine shell scripts

This guide is for the common case where a shell script works on one Linux image but
fails in another with `command not found`, `not found`, or exit code `127`.
It also covers the search phrases **run a shell script in Debian Ubuntu Alpine**,
**test a shell installer across distributions**, and **why ShellCheck passed but CI failed**.

## The short answer

Static analysis can check shell syntax. It cannot know which binaries are installed in
the image that will execute the script. Run the script in each target distribution and
keep the result in CI:

```yaml
name: Shell runtime compatibility

on:
  pull_request:
  push:

jobs:
  shell-runtime:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: Mresyzz/opsscript-gate@v0.9.0
        with:
          script-path: scripts/install.sh
          shell: auto
```

The action runs the target script in Debian 12, Ubuntu 22.04, Ubuntu 24.04, and
Alpine 3.20 containers. It reports the distribution, exit code, line number, missing
command, and a remediation hint in the workflow summary.

## `apt-get: not found` on Alpine

Debian and Ubuntu use APT. Alpine uses `apk`. This script is syntactically valid but
assumes the wrong package manager:

```sh
#!/bin/sh
set -eu
apt-get --version
```

The runtime matrix is expected to look like this:

```text
debian:12-slim  PASS
ubuntu:22.04    PASS
ubuntu:24.04    PASS
alpine:3.20     FAIL  exit 127: apt-get: not found
```

If the installer is intended to support both families, branch on the command that is
actually available and keep package names distribution-specific:

```sh
if command -v apt-get >/dev/null 2>&1; then
    apt-get --version
elif command -v apk >/dev/null 2>&1; then
    apk --version
else
    echo 'Unsupported package manager' >&2
    exit 1
fi
```

Do not install packages just to hide the failure unless that package is a documented
prerequisite of the installer. OpsScript Gate supports explicit `packages` setup when
the test genuinely needs tools such as `curl`; see [configuration](configuration.md).

## Other runtime failures that look similar

### `/bin/bash: not found`

Minimal Alpine images do not include Bash by default. Use a POSIX-compatible script for
`/bin/sh`, test a recognized Bash shebang with `shell: auto` or `shell: shebang`, or
choose an image that documents Bash as a prerequisite.

### `curl`, `jq`, or `git: not found`

Minimal images intentionally omit many convenience tools. A passing Ubuntu run does
not prove that the same command exists on Alpine. Either declare the tool through the
Action's `packages` input or make the installer detect and explain the prerequisite.

### `read` hangs or exits at end of file

CI execution has no interactive terminal and standard input is disconnected. Add a
noninteractive path to the installer. Increasing the timeout does not make an
interactive installer safe for unattended use.

## Run the same diagnosis locally

The CLI requires Python 3.10+ and a reachable Docker engine:

```bash
pip install opsscript-gate
opsscript-gate doctor
opsscript-gate run ./scripts/install.sh
```

Use `opsscript-gate run --dry-run` to preview script selection without Docker. For a
repository with several scripts, `opsscript-gate run` discovers shell files and reports
the planned container executions before starting them.

## Why ShellCheck and runtime testing are complementary

ShellCheck catches quoting, expansion, and shell-dialect mistakes in source code.
Runtime testing catches missing commands, missing interpreters, package-manager
assumptions, and noninteractive behavior in the actual target images. Running both
checks answers two different questions: **is this shell source valid?** and **does it
run in the Linux environments we support?**

See the [Alpine incompatibility example](../examples/alpine-incompatibility/README.md),
[troubleshooting guide](troubleshooting.md), or the [interactive demo](https://mresyzz.github.io/opsscript-gate/).
