# Awesome Lists 提交收录指南与 PR 模板

提交至权威的 GitHub Awesome Lists 可以带来长尾的高权重自然流量和反向链接。以下为推荐提交的目标仓库与对应的建议提交内容。

---

## 1. 目标仓库一: `sdras/awesome-actions`
- **仓库地址**: https://github.com/sdras/awesome-actions
- **推荐分类小节**: `Continuous Integration` 或 `Utility`
- **PR 标题**:
  ```text
  Add OpsScript Gate to Continuous Integration section
  ```
- **添加的 Markdown 行**:
  ```markdown
  - [OpsScript Gate](https://github.com/Mresyzz/opsscript-gate) - Run shell scripts across Debian, Ubuntu, and Alpine containers to catch runtime compatibility failures.
  ```

---

## 2. 目标仓库二: `alebcay/awesome-shell`
- **仓库地址**: https://github.com/alebcay/awesome-shell
- **推荐分类小节**: `Testing` 或 `Continuous Integration`
- **PR 标题**:
  ```text
  Add opsscript-gate to Testing section
  ```
- **添加的 Markdown 行**:
  ```markdown
  - [OpsScript Gate](https://github.com/Mresyzz/opsscript-gate) - Drop-in runtime compatibility gate for Linux shell scripts across multiple container distributions.
  ```

---

## 3. 目标仓库三: `uhub/awesome-devops`
- **仓库地址**: https://github.com/uhub/awesome-devops
- **推荐分类小节**: `CI/CD & Automation Tools`
- **PR 标题**:
  ```text
  Add OpsScript Gate to CI/CD tools
  ```
- **添加的 Markdown 行**:
  ```markdown
  - [OpsScript Gate](https://github.com/Mresyzz/opsscript-gate) - Lightweight multi-distro container gate verifying shell script portability before release.
  ```

---

## 提交 PR 时的通用描述模板 (PR Body)

```markdown
### Summary

This PR adds [OpsScript Gate](https://github.com/Mresyzz/opsscript-gate) to the list.

- **What it does**: A lightweight GitHub Action & CLI that runs shell scripts across Debian, Ubuntu, and Alpine Docker containers to catch runtime compatibility failures (missing package managers, unhandled interactive prompts, missing interpreters) that static analysis cannot catch.
- **License**: MIT
- **Format compliance**: Formatted alphabetically and according to the repository contribution guidelines.
```
