#!/bin/sh
# fail_hang.sh: Attempts to prompt for user interaction via stdin
set -e

echo "Prompting operator for interactive confirmation..."

# When stdin is redirected from /dev/null, read immediately hits EOF and returns code 1
if read -r USER_INPUT; then
    echo "Received input: $USER_INPUT"
else
    echo "Error: Interactive input required but standard input is closed (/dev/null)." >&2
    exit 1
fi

if [ -z "$USER_INPUT" ]; then
    echo "Error: Empty input provided." >&2
    exit 1
fi

echo "Operation confirmed."
exit 0
