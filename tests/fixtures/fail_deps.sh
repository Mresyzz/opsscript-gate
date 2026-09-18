#!/bin/sh
# This will pass on Debian/Ubuntu but fail on Alpine which uses apk
apt-get update -y
exit $?
