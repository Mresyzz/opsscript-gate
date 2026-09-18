#!/bin/sh
# prompt_confirm.sh: Demonstrates an unhandled interactive prompt
# In an unconfigured CI, this hangs forever. In OpsScript Gate, it fails fast.
set -e

echo "[?] Confirm deployment rollout:"
if read -r USER_CONFIRM; then
    echo "Confirmed: $USER_CONFIRM"
else
    echo "[!] Standard input is closed (/dev/null). Interactive prompt cannot proceed." >&2
    exit 1
fi
