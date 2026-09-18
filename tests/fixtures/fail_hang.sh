#!/bin/sh
echo "Waiting for user input..."
# This would hang indefinitely if stdin is connected.
# Since we run with stdin disconnected (or redirected from /dev/null),
# this should fail immediately or EOF depending on the shell,
# preventing a timeout. In many cases `read -p` exits 1 or 0 without hanging when stdin is closed.
# To enforce a true hang that ONLY a timeout can fix (if timeout wasn't there), we can use sleep,
# but the requirement states: "Tries reading from stdin (fails/exits immediately due to /dev/null)".
# So we just do `read`
read dummy
# If it doesn't fail, we exit 1 to show it's an error in logic
if [ -z "$dummy" ]; then
    exit 1
fi
exit 0
