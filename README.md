# opsscript-gate

[![CI](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/test.yml)
[![Demo](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml/badge.svg)](https://github.com/Mresyzz/opsscript-gate/actions/workflows/demo.yml)
[![GitHub Release](https://img.shields.io/github/v/release/Mresyzz/opsscript-gate?color=blue)](https://github.com/Mresyzz/opsscript-gate/releases)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Matrix](https://img.shields.io/badge/distros-Debian%20%7C%20Ubuntu%20%7C%20Alpine-orange.svg)](#默认测试矩阵)

> 面向 Linux 运维 Shell 脚本的轻量级、无特权容器跨发行版兼容性预演门禁与 GitHub Action。

在脚本合并至 `main` 分支或打 Tag 发版前，`opsscript-gate` 会拉起一套无特权的隔离容器矩阵自动执行脚本，在秒级时间内完成全流程兼容性预演，拦截命令缺失（如 Alpine 缺 `apt` / 工具链）、Bashism 语法假定、交互式输入挂死以及换行符污染等问题。

---

## 解决的问题

运维 Shell 脚本在跨发行版（Debian / Ubuntu / Alpine）交付时最容易出现以下生产隐患：

1. **发行版工具链与包管理器断层**：
   - 在 Ubuntu/Debian 上测试通过的脚本，往往隐式依赖 `apt-get`、`systemctl` 或特定 GNU Coreutils 参数；
   - 一旦在轻量基础镜像 Alpine（基于 musl libc 与 BusyBox，仅支持 `apk`）中运行，会直接因命令不存在报 `exit 127` 崩溃。

2. **未受控的标准输入导致 CI 永久挂死**：
   - 脚本中若偶发包含 `read -p`、交互式确认或第三方安装器未传 `-y / --non-interactive`；
   - 在 CI 流水线中会因为无限期等待键盘输入而耗尽构建机额度，最终触发超时强杀。

3. **CRLF 换行符导致的假性语法错误**：
   - Windows 平台开发者检出或编辑脚本后容易引入 `\r\n`；
   - 容器挂载后 Linux 解释器会将 `\r` 识别为命令一部分，抛出诡异的 `\r: command not found`。

4. **隐蔽的非零退出码被遗漏**：
   - 脚本内部缺少退出状态传播检查，中间关键步骤失败却因后续无关操作成功而返回 0，导致损坏环境继续上线。

---

## 运行效果

### 1. 成功预演终端输出 (ASCII Table)

```text
+--------------------+----------+-----------+------------+---------+
| Distro             | Status   | Exit Code | Duration   | Details |
+--------------------+----------+-----------+------------+---------+
| debian:12-slim     | PASS     | 0         | 1.15s      | OK      |
| ubuntu:22.04       | PASS     | 0         | 1.08s      | OK      |
| ubuntu:24.04       | PASS     | 0         | 1.12s      | OK      |
| alpine:3.20        | PASS     | 0         | 0.45s      | OK      |
+--------------------+----------+-----------+------------+---------+
Total duration: 3.80s | Result: PASSED
```

### 2. 拦截失败案例展示 (Alpine 捕获 `apt-get` 缺失)

当对依赖 `apt-get` 的脚本运行门禁时，`opsscript-gate` 能够立即定位 Alpine 故障并抓取最后 15 行错误日志：

```text
+--------------------+----------+-----------+------------+----------------------------------------------------+
| Distro             | Status   | Exit Code | Duration   | Details                                            |
+--------------------+----------+-----------+------------+----------------------------------------------------+
| debian:12-slim     | PASS     | 0         | 1.20s      | OK                                                 |
| ubuntu:22.04       | PASS     | 0         | 1.10s      | OK                                                 |
| ubuntu:24.04       | PASS     | 0         | 1.18s      | OK                                                 |
| alpine:3.20        | FAIL     | 127       | 0.48s      | Script failed with non-zero exit code: 127         |
+--------------------+----------+-----------+------------+----------------------------------------------------+
Total duration: 3.96s | Result: FAILED

============================================================
Failed Distributions - Output Snippets (last 15 lines):
============================================================

--- [alpine:3.20] (FAIL) ---
/tmp/target_script.sh: line 5: apt-get: not found
```

### 3. GitHub Actions 概览集成 (Step Summary)

在 GitHub CI 环境中运行时，会自动检测 `$GITHUB_STEP_SUMMARY`，将 Markdown 表格与可折叠诊断日志直接渲染至 Action Job 详情页：

| Distro | Status | Exit Code | Duration | Message |
| :--- | :---: | :---: | :---: | :--- |
| `debian:12-slim` | ✅ PASS | `0` | `1.20s` | - |
| `ubuntu:22.04` | ✅ PASS | `0` | `1.10s` | - |
| `ubuntu:24.04` | ✅ PASS | `0` | `1.18s` | - |
| `alpine:3.20` | ❌ FAIL | `127` | `0.48s` | Script failed with non-zero exit code: 127 |

---

## 隔离与安全设计

- **绝对无特权容器**：严禁 `--privileged`，显式剥离所有 Linux Capabilities（`cap_drop=["ALL"]`），禁止挂载任何宿主机敏感路径。
- **严格只读挂载**：待测脚本以只读模式挂载至容器内（`{"bind": "/tmp/target_script.sh", "mode": "ro"}`）。
- **非交互防死锁机制**：关闭 stdin 与 TTY（`stdin_open=False`, `tty=False`），通过 `/bin/sh /tmp/target_script.sh </dev/null` 将输入强制绑定至空设备，并注入环境变量 `DEBIAN_FRONTEND=noninteractive` 与 `CI=true`。脚本若尝试从终端读取输入将立即失败退出，而非卡死流水线。
- **硬超时杀进程保障**：默认配置 60 秒硬超时，轮询到达超时阈值后立即执行 `container.kill()` 强杀，标记状态为 `TIMED_OUT`。
- **零僵尸容器保障**：容器生命周期受严格受控的 `finally` 块管理，无论脚本成功、返回非零、被强杀或抛出异常，必定触发 `container.remove(force=True)`。
- **换行符防御**：自动扫描并规整 Windows CRLF (`\r\n`) 为标准 Unix LF (`\n`)，杜绝换行符假性失败。
- **严格 POSIX /bin/sh 执行基线**：统一采用基础解释器 `/bin/sh` 执行。此举并非单纯进行静态字符串解析，而是以 Alpine/BusyBox 的真实环境作为试金石，在发版前严格校验脚本是否兼容标准 POSIX 语义，拦截在未声明环境下使用 Bashism 语法（如 Bash 数组、`[[ ... ]]`、进程替换等）而引发的跨系统故障。

---

## 默认测试矩阵

| 镜像标签 | 特点与验证侧重点 |
| :--- | :--- |
| `debian:12-slim` | Debian 官方精简镜像，验证基于 glibc 与 apt 的基础环境兼容性 |
| `ubuntu:22.04` | 生产常见 LTS 版本，验证主流长期支持环境中的运行状态 |
| `ubuntu:24.04` | 较新的 LTS 版本，验证最新系统调用与默认工具链更新后的行为 |
| `alpine:3.20` | 基于 musl libc 与 BusyBox，检验标准 POSIX 兼容性与极简环境缺失依赖 |

---

## 快速上手

### 1. 本地命令行

环境要求：Python >= 3.10，宿主机具备可用的 Docker 环境。

```bash
# 从官方代码库安装
pip install git+https://github.com/Mresyzz/opsscript-gate.git

# 对目标脚本执行门禁预演（默认执行 4 个发行版矩阵）
opsscript-gate run ./scripts/setup.sh

# 自定义测试矩阵与超时时间
opsscript-gate run ./scripts/setup.sh \
  --matrix "debian:12-slim,alpine:3.20" \
  --timeout 30 \
  --format table
```

### 2. 作为 GitHub Action 集成到生产 CI

在仓库工作流文件（如 `.github/workflows/script-gate.yml`）中添加：

```yaml
name: Script Compatibility Gate

on:
  pull_request:
    paths:
      - 'scripts/**'
  push:
    branches: [ main ]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Run OpsScript Gate
        uses: Mresyzz/opsscript-gate@v0.1.0
        with:
          script-path: 'scripts/setup.sh'
          matrix: 'debian:12-slim,ubuntu:22.04,ubuntu:24.04,alpine:3.20'
          timeout: '60'
          format: 'table'
```

---

## CLI 参数说明

`opsscript-gate run <script_path> [options]`

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `script_path` | 路径 (位置参数) | 必填 | 待测试的 Shell 脚本路径 |
| `--matrix` | 字符串 | 4 个默认镜像 | 逗号分隔的镜像列表（如 `debian:12-slim,alpine:3.20`） |
| `--timeout` | 整数 | `60` | 单容器硬超时上限（秒） |
| `--format` | 选项 | `table` | 报告输出格式：`table`（终端对齐表格）、`markdown`、`json` |
| `--version` | 标志 | - | 查看当前版本号 |
| `-h, --help` | 标志 | - | 查看完整帮助说明 |

#### 退出码规范：
- **`0`**：全部指定发行版均通过预演（`PASS`）。
- **`1`**：任一发行版失败（`FAIL`）、超时（`TIMED_OUT`）或发生执行异常（`ERROR`）。

---

## 本地开发与测试套件

测试套件已实现纯 Mock 隔离，无需依赖宿主机 Docker 进程即可秒级完成回归：

```bash
# 安装开发与测试依赖
pip install -e .[test]

# 运行快速单元测试（纯 Mock 覆盖所有生命周期与边界）
pytest -v -m "not integration"

# 运行完整测试（包含真实容器拉起测试，需 Docker 运行中）
pytest -v
```

---

## 开源许可

本项目遵循 [MIT License](LICENSE) 协议开源。
