# V2EX 中文技术社区发帖模版

## 1. 发布建议
- **节点**: [分享创造](https://v2ex.com/go/create) 或 [程序员](https://v2ex.com/go/programmer)
- **时间**: 工作日上午 10:30 ~ 11:30 或 下午 14:30 ~ 15:30（摸鱼高峰期流量最大）

---

## 2. 标题 (Title)
```text
为什么 ShellCheck 检查全绿的运维脚本，在 Alpine 容器里依然会挂？做了一个开源轻量预演门禁 OpsScript Gate
```

---

## 3. 正文模版 (Markdown)

相信很多做运维、后端或写开源工具的朋友都写过类似 `curl -fsSL https://.../install.sh | bash` 的安装脚本。

我们在本地 Ubuntu / Mac 下自测通过，CI 里配置了著名的静态检查工具 **ShellCheck**，代码一查全绿，0 warnings、0 errors。满心欢喜发版后，很快就会收到 Issue：
- “在 Alpine Linux 下执行报错：`line 4: apt-get: not found`”
- “精简容器镜像里没有 `/bin/bash`，只有 BusyBox `/bin/sh`，脚本直接退出”
- “脚本里的某个命令突然在交互式等待输入，CI 流水线直接卡死直到超时”

### 为什么 ShellCheck 检查全绿依然会挂？

因为 ShellCheck 是**纯静态 AST 分析器**。它能帮你揪出未加引号的变量扩展、语法错误或 Bashism，但它**无法感知你的脚本运行在什么具体的系统基底上**。
- 语法是标准的 POSIX，但调用的外部命令在 Alpine/Debian-slim 镜像里根本不存在；
- 脚本里的 Shebang 声明了 `#!/bin/bash`，但目标系统只有 `dash` 或 `ash`。

为此我做了一个轻量级、开箱即用的跨发行版自动化执行门禁：**OpsScript Gate**。

- 🔗 **GitHub**: https://github.com/Mresyzz/opsscript-gate
- 📦 **PyPI**: https://pypi.org/project/opsscript-gate/
- 🏷️ **开源协议**: MIT

---

### 它能做什么？

1. **多发行版矩阵预演**：
   默认在标准的 `debian:12-slim`、`ubuntu:22.04`、`ubuntu:24.04` 和 `alpine:3.20` 纯净容器中同时预演运行你的脚本。
2. **严密的无特权安全沙箱**：
   强制无特权（`privileged=False`）、剥离全部内核 Capabilities（`CAP_DROP=ALL`）、脚本文件只读挂载（`:ro`）、禁止提权（`no-new-privileges`）。
3. **输入挂起断流防御**：
   强制断开标准输入（`</dev/null`）并注入非交互环境变量。一旦脚本试图弹出交互式确认（如未加 `-y` 的安装命令），立即报错退出，绝不会挂死 CI。
4. **缺失命令精准提取（v0.3.0 新特性）**：
   自动识别退出码 127 与 Shell 报错特征，直接在终端表格与 GitHub Step Summary 中展示 `missing command: apt-get`，不用翻查海量执行日志。
5. **极简接入**：
   本地一行即可运行：
   ```bash
   pip install opsscript-gate
   opsscript-gate run ./scripts/setup.sh
   ```
   GitHub Actions 中只需 5 行代码：
   ```yaml
   - uses: actions/checkout@v7
   - uses: Mresyzz/opsscript-gate@v0.3.0
     with:
       script-path: scripts/setup.sh
       shell: auto
   ```

项目的核心定位是：
> **“ShellCheck tells you if your script looks portable. OpsScript Gate checks if it actually runs there.”**
> （ShellCheck 验证脚本语法看起来是否便携，OpsScript Gate 验证它在真实环境里到底能不能跑起来。）

欢迎大家 Star、试用或提意见，也期待与大家交流日常编写跨系统 Shell 脚本时的避坑经验！
