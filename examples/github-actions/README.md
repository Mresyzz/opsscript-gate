# GitHub Actions Integration Example

This example shows a GitHub Actions workflow for checking a shell script on pull requests.

Copy `workflow.yml` into your repository at `.github/workflows/script-gate.yml` and point `script-path` to the script you want to validate. The example uses the published v0.9.4 release.

For a downloading installer, use [installer-smoke.yml](installer-smoke.yml) and
adapt its installed binary path and smoke command. This checks that installation
actually produced a working binary, even when the installer returns zero after
a failed download. See the [installer smoke test guide](../../docs/installer-smoke-test.md)
for the result boundaries and setup instructions.
