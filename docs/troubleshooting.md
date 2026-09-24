# Shell script works on Ubuntu but fails on Alpine

ShellCheck analyzes shell source. Runtime compatibility tests also exercise the
commands, interpreters and utilities available in each target image. Use both.

## `apt-get: not found` on Alpine

Alpine uses `apk`; Debian and Ubuntu use APT. A script can be valid POSIX shell and
still assume the wrong package manager. Detect supported environments explicitly or
limit the test matrix to the environments your script actually supports. Do not
replace package names blindly: names and packages can differ across distributions.

```sh
#!/bin/sh
set -eu
if command -v apt-get >/dev/null 2>&1; then
    apt-get --version
elif command -v apk >/dev/null 2>&1; then
    apk --version
else
    echo 'Unsupported package manager' >&2
    exit 1
fi
```

This example only queries versions; it does not install packages.

## `/bin/bash` is missing

The minimal Alpine image does not supply Bash by default. `--shell auto` and
`--shell shebang` honor recognized Bash shebangs and expose this missing dependency.
Use POSIX-compatible shell syntax if Alpine is a supported target, or supply a
custom image containing Bash. `--shell posix` executes with `/bin/sh`; it does not
translate Bash syntax or install an interpreter.

## `source`, relative paths or sibling files fail

Only the target script is mounted, at `/tmp/target_script.sh`. Repository directories,
fixtures, sourced helpers and other assets are not mounted. The current product is
suited to standalone scripts. A passing result is not a full repository integration
test. Use a custom test image for dependencies, or keep your existing project-level CI.

## A prompt fails or the script times out

Stdin is disconnected, no TTY is provided, and CI/noninteractive variables are set.
This exposes interactive installers that would otherwise block unattended CI.
Give your script a noninteractive path. Increase `--timeout` only for expected work.

## Nothing runs, or too many scripts are found

Start with `opsscript-gate run --dry-run`. Exclude deliberately failing fixtures or
manual maintenance scripts. More than 20 selected scripts now fails explicitly;
`--max-scripts 50` permits a larger set. Preview shows total container executions.

## Docker is unavailable

Actual execution requires a reachable Docker engine running Linux containers.
Check `docker version` in the same environment as the CLI. On Windows/WSL, ensure
your chosen Docker installation exposes its engine to that environment. `init`
and `--dry-run` work without an engine but do not prove scripts will pass.

## Downloads fail after `init`

Generated projects default to `network: none`. For trusted scripts that genuinely
need downloads, set `network: bridge` or pass `--network bridge`. Containers remain
resource-limited and capabilities are dropped; operations requiring extra privileges
may still fail. Do not treat this tool as a sandbox for untrusted code.
