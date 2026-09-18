#!/bin/sh
# pass_basic.sh: Basic POSIX file and environment operations
set -e

echo "Starting basic cross-distro compatibility validation..."

# Verify standard utilities available on all POSIX distros
TMP_TEST_DIR=$(mktemp -d /tmp/opsscript_test.XXXXXX)
trap 'rm -rf "$TMP_TEST_DIR"' EXIT

TEST_FILE="$TMP_TEST_DIR/sample.txt"
echo "OpsScript Gate validation payload" > "$TEST_FILE"

if [ ! -f "$TEST_FILE" ]; then
    echo "Error: Failed to write test file" >&2
    exit 1
fi

CONTENT=$(cat "$TEST_FILE")
if [ "$CONTENT" != "OpsScript Gate validation payload" ]; then
    echo "Error: Content mismatch" >&2
    exit 1
fi

echo "Basic compatibility passed successfully on $(uname -s)!"
exit 0
