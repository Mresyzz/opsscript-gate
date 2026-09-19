# Hacker News Show HN 推广指南与发帖模版

## 1. 发布建议
- **目标板块**: [Hacker News Show HN](https://news.ycombinator.com/showhn.html)
- **黄金发布时间**:
  - 北京时间: **周二至周四 晚上 21:00 ~ 23:00**
  - 对应美西时间: 早上 06:00 ~ 08:00（美东 09:00 ~ 11:00，此时 HN 流量高峰开启）
- **发帖建议**:
  - 不要带营销色彩，HN 极客崇尚第一性原理、代码开源、架构简单、无废话。
  - 发布后在首楼积极、专业地回复评论。

---

## 2. 标题 (Title)
```text
Show HN: OpsScript Gate – ShellCheck passes, but will your script run on Alpine?
```
*(备选标题: Show HN: OpsScript Gate – Zero-config container matrix gate for shell scripts)*

---

## 3. 正文 (URL / Text)
*如果是发 Text Post (推荐)，直接粘贴以下内容；如果发 Link Post，将 URL 设为 `https://github.com/Mresyzz/opsscript-gate` 并在首楼回复以下内容:*

```markdown
Hey HN,

We've all seen this happen: a team member writes an install.sh or bootstrap script, runs ShellCheck (0 warnings, valid POSIX syntax), and ships it.

Then an issue arrives:
"Script failed on Alpine Linux: line 4: apt-get: not found"
(or "bash: not found", or a subtle dash vs ash incompatibility).

Static analysis (like ShellCheck) is indispensable for quoting, AST validity, and detecting bashisms. But it cannot know whether the utilities, package managers, interpreters, or flags your script relies on actually exist inside minimal runtime environments.

I built OpsScript Gate to solve this: https://github.com/Mresyzz/opsscript-gate

What it does:
- Runs your target script in isolated, unprivileged Docker containers across Debian 12, Ubuntu 22.04, Ubuntu 24.04, and Alpine 3.20.
- Hardened container defaults: CAP_DROP=ALL, no-new-privileges, read-only script mounts, and stdin redirected from /dev/null so scripts can't deadlock CI on unhandled interactive prompts.
- Extracts high-confidence failure diagnostics (e.g. requires exit code 127 + shell 'not found' pattern) to tell you exactly which command was missing without digging through logs.
- Can be used locally via CLI (`pip install opsscript-gate`) or dropped into GitHub Actions in 5 lines of YAML:

```yaml
- uses: actions/checkout@v7
- uses: Mresyzz/opsscript-gate@v0.3.0
  with:
    script-path: scripts/setup.sh
    shell: auto
```

The positioning:
"ShellCheck tells you if your script looks portable.
OpsScript Gate checks if it actually runs there."

It is fully open source (MIT). I'd love to hear your thoughts, feedback, and how you currently validate multi-distro shell scripts in CI!
```

---

## 4. 常见 HN 评论预设答疑 (Q&A Cheatsheet)

- **Q: Why not just use Docker matrix in GitHub Actions directly?**
  - **A**: Writing a custom matrix for every repository requires copying 50+ lines of workflow YAML, managing volume mounts, handling CRLF carriage returns from Windows contributors, setting timeouts, and parsing logs when a distro fails. OpsScript Gate packages all of this into a single self-contained action/CLI step with unified summary reporting.

- **Q: Is it safe to run untrusted PR scripts?**
  - **A**: OpsScript Gate runs containers with `privileged=False`, drops all Linux capabilities (`CAP_DROP=ALL`), sets `no-new-privileges:true`, and mounts the script as read-only (`:ro`). While Docker containerization is not a complete hypervisor sandbox, these defaults strictly limit attack surface during CI evaluation.
