# Interactive Hang Defense Example

In continuous integration pipelines, scripts that unexpectedly request user confirmation (`read`) often cause runners to hang until the job-level timeout kills them hours later.

OpsScript Gate disconnects stdin and maps it directly to `/dev/null`. This turns what would be an indefinite hang into an immediate, non-zero failure so you can add non-interactive flags (e.g. `-y` or `-f`).

## How to run

```bash
opsscript-gate run ./examples/interactive-hang/prompt_confirm.sh
```

## Expected Outcome

The script exits immediately with code `1` rather than blocking execution.
