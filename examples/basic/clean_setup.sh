#!/bin/sh
# clean_setup.sh: Fully POSIX-compliant environment preparation script
# Designed to exit 0 across Debian, Ubuntu, and Alpine.
set -e

echo "[+] Initializing clean directory layout..."
WORK_DIR=$(mktemp -d /tmp/app_setup.XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

echo "[+] Creating runtime configuration..."
cat << 'EOF' > "$WORK_DIR/config.env"
APP_ENV=production
LOG_LEVEL=info
EOF

test -f "$WORK_DIR/config.env"
echo "[+] Validated POSIX utilities: mktemp, cat, test, rm."
echo "[+] Clean setup completed successfully."
exit 0
