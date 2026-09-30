# Alpine Incompatibility Example

This example shows a common portability issue: a script calls `apt-get`, which is
available on Debian and Ubuntu but not on Alpine, where the package manager is `apk`.

Static linters like ShellCheck usually cannot determine if `apt-get` exists on the target runtime system, but OpsScript Gate catches this immediately.

## How to run

```bash
opsscript-gate run ./examples/alpine-incompatibility/apt_dependency.sh
```

## Expected Outcome

- `debian:12-slim`: PASS (exit code 0)
- `ubuntu:22.04`: PASS (exit code 0)
- `ubuntu:24.04`: PASS (exit code 0)
- `alpine:3.20`: **FAIL (exit code 127)** — `apt-get: not found`
