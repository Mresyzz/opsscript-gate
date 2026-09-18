---
name: Distribution Support Request
about: Request adding a new Linux distribution or version to the test matrix
title: "[DISTRO] Support "
labels: ["distro-matrix"]
assignees: ""
---

**Proposed Distribution Image**
- Image tag: [e.g. fedora:40, rockylinux:9, archlinux:latest]
- Public Registry: [e.g. Docker Hub official, Quay.io]

**Rationale & Industry Use Case**
Why is this distribution important for Linux ops scripts compatibility pre-checks?

**Default Shell & Init Characteristics**
- Default `/bin/sh` provider: [e.g. dash, bash, busybox, ash]
- Default Package Manager: [e.g. dnf, pacman, apk, apt]
- Does the minimal container image boot cleanly without interactive setup? [Yes/No]

**Sample Verification Script**
If possible, provide a sample ops script that typically runs on this distro.
