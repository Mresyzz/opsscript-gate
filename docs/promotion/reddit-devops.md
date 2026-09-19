# Reddit 社区推广指南与发帖模版

## 1. 目标 Subreddit
1. **r/devops** (重点，讨论 CI/CD 与自动化脚本质量)
2. **r/bash** (讨论 Shell 脚本编写与跨平台兼容)
3. **r/linuxadmin** (系统管理与运维实践)
4. **r/githubactions** (GitHub Actions 用户群体)

---

## 2. 标题 (Title 备选)
- **选项 A (痛点直击型)**:
  `ShellCheck said our script was portable. Alpine killed it instantly. So I built a 0-config container matrix gate.`
- **选项 B (工具分享型)**:
  `OpsScript Gate – A lightweight GitHub Action & CLI to test shell scripts across Debian, Ubuntu, and Alpine containers`

---

## 3. 正文模版 (Post Body)

```markdown
Hi r/devops!

Like many of you, I maintain bootstrap scripts (`install.sh`, `setup.sh`) that users run across various Linux distros.

For a long time, we relied solely on **ShellCheck** in our CI pipeline. ShellCheck is fantastic for finding unquoted variables and syntax bugs, but it consistently missed environment-specific runtime issues:
- Calling `apt-get` on Alpine Linux (which uses `apk`)
- Requiring `/bin/bash` when the base container only has `/bin/sh`
- A subtle subshell or flag behavior differences between Debian `dash` and Alpine `ash`
- Scripts freezing the CI runner indefinitely on an unexpected `read -p` prompt

Running full multi-machine matrices or writing custom Docker boilerplate for every repo became tedious, so I created **OpsScript Gate**:

🔗 GitHub: https://github.com/Mresyzz/opsscript-gate
📦 PyPI: `pip install opsscript-gate`

### What it does:
1. **Multi-Distro Execution**: Runs your script across `debian:12-slim`, `ubuntu:22.04`, `ubuntu:24.04`, and `alpine:3.20` in parallel or series.
2. **Strict Security Defaults**: Unprivileged containers, all Linux capabilities dropped (`CAP_DROP=ALL`), read-only mount, and `no-new-privileges`.
3. **Deadlock & Hang Prevention**: Automatically redirects stdin from `/dev/null` and enforces non-interactive environment variables, killing interactive prompts immediately.
4. **Actionable Diagnostics**: Uses dual-signal detection (exit 127 + shell pattern matching) to identify missing commands directly in the summary table without requiring users to parse hundreds of lines of logs.
5. **Drop-in CI Integration**: 5 lines of YAML in GitHub Actions:

```yaml
- uses: actions/checkout@v7
- uses: Mresyzz/opsscript-gate@v0.3.0
  with:
    script-path: scripts/install.sh
    shell: auto
```

Project positioning:
> *"ShellCheck tells you if your script looks portable. OpsScript Gate checks if it actually runs there."*

Feedback, issues, and contributions are very welcome! How do you currently guard against distro runtime breakages in your deployment scripts?
```
