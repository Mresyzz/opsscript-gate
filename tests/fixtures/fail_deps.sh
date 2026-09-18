#!/bin/sh
# fail_deps.sh: Uses apt-get which succeeds on Debian/Ubuntu but fails on Alpine (code 127)
set -e

echo "Checking Debian/Ubuntu package manager..."
apt-get --version

echo "apt-get is available on this system."
exit 0
