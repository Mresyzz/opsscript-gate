# Verify what an installer actually installed

A shell script can print “Installation finished” and return zero after a failed
download or extraction. OpsScript Gate checks the exit status of the command it
runs; it cannot infer which files an arbitrary installer should have created.
For an installer, make that contract explicit: install the binary, check that it
exists, then execute a harmless smoke command inside the same container.

## Copy the workflow

Copy [installer-smoke.yml](../examples/github-actions/installer-smoke.yml) into
`.github/workflows/installer-smoke.yml` in your project. Edit:

- `install.sh` to your standalone installer path.
- `$HOME/.local/bin/mytool` to the installed binary path.
- `--version` to a noninteractive command that demonstrates the installed binary
  can start. It must return nonzero on failure.
- The packages, timeout and distribution matrix to match your supported setup.
- The trigger paths to include release packaging configuration if it affects the
  archive name or layout.

The workflow embeds the current checked-out installer into a temporary script.
It runs the installer in a subshell and checks the binary afterwards. Even an
installer with an explicit `exit 0` cannot skip the check. A nonzero installer
status is preserved. The check and installer run in the **same container**;
checking for the installed binary on the GitHub runner would test a different
filesystem.

The default example enables network access to download release assets and adds
Bash, curl, CA certificates and tar. Those are test prerequisites, not evidence
that your installer provisions them. If you promise installation on a bare
image, also test that scenario separately.

## Interpret the result

- An executable binary and a successful smoke command prove the tested artifact
  could install and start in that container during that run.
- A missing binary fails even if the installer returned zero.
- A downloaded binary that cannot start also fails.
- HTTP errors, rate limits and changed release assets can affect the result.
  Inspect the saved report before attributing a failure to a distribution.

This is not a test of your application's complete behavior. Containers share
the host kernel and do not represent a full booted machine. OpsScript Gate mounts
only the target script; installers that need sibling repository files require a
different integration setup.

## A failure this check caught

In a [public fork validation of Latitude's CLI installer](https://github.com/Mresyzz/cli/actions/runs/38145896335),
the Ubuntu 22.04 job downloaded content that could not be extracted as gzip. The
installer continued and printed “Installation finished”. An installation check
then failed because `$HOME/.lsh/lsh` was absent. Debian 12, Ubuntu 24.04 and Alpine
3.20 passed in that run. This demonstrates a caught installation failure, not a
proven Ubuntu-specific defect or an endorsement by the upstream maintainers.
