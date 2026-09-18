#!/bin/sh
# apt_dependency.sh: Demonstrates typical Debian/Ubuntu assumption
# Passes on Debian & Ubuntu, but immediately crashes on Alpine (exit 127).
set -e

echo "[+] Updating system package catalog..."
apt-get update -qq

echo "[+] Package catalog updated."
exit 0
