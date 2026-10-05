# GitHub Actions Integration Example

This example shows a GitHub Actions workflow for checking a shell script on pull requests.

Copy `workflow.yml` into your repository at `.github/workflows/script-gate.yml` and point `script-path` to the script you want to validate. The example targets the local v0.9.2 candidate; change the tag to a published release before using it from another repository.
