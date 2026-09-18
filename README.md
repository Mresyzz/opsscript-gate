# OpsScript Gate (`opsscript-gate`)

面向 Linux 运维 Shell 脚本的轻量级、无特权容器跨发行版兼容性预演门禁与 GitHub Action。

---

## 📖 项目背景

在日常云原生与 Linux 运维场景中，Shell 脚本常常承担环境初始化、依赖配置、服务自愈和发布部署等关键任务。然而，运维脚本在发版前往往面临跨发行版兼容性隐患：
- **软件包管理器与核心命令缺失**：Debian/Ubuntu 依赖 `apt-get`、`systemctl`，而在轻量级 Alpine 中只有 `apk`，且默认采用 BusyBox 精简命令集，常因缺失工具导致 `command not found (exit 127)`。
- **未捕获的静默错误**：脚本缺少 `set -e` 或管道错误处理，在部分发行版中执行异常却静默退出。
- **交互等待导致 CI 永久挂死**：脚本意外调用 `read`、交互式包安装提示，导致持续等待标准输入而阻塞流水线。

`opsscript-gate` 旨在作为发布前的一道轻量门禁，通过无特权瞬态容器并行/串行预演运行，即时捕获跨系统异常并输出整洁的汇总报表。

---

## 🛡️ 核心安全边界与隔离红线（Strict Security Boundary）

1. **绝对无特权容器（Unprivileged Containers）**：
   - 严禁启用特权模式（`--privileged`）。
   - 严禁授予特权 Capabilities（如 `CAP_SYS_ADMIN` 等）。
   - 待测宿主机脚本显式以只读卷挂载（`:ro`），严禁挂载宿主机敏感路径（如 Docker Socket、`/etc` 等）。
2. **强制硬超时强杀（Hard Timeout Interruption）**：
   - 单个镜像预演默认设置 60 秒硬超时（可通过参数自定义）。
   - 超时后立即对容器发出 `SIGKILL` 强杀信号（`container.kill()`），防止任何后台死锁进程残留，并标记状态为 `TIMED_OUT`。
3. **彻底防范交互挂死（Non-interactive Anti-hang）**：
   - 容器禁用 TTY 与标准输入（`stdin_open=False`, `tty=False`）。
   - 容器内执行脚本时强制定向至 `/dev/null`（`</dev/null`）。
   - 强制注入非交互环境变量：`DEBIAN_FRONTEND=noninteractive`、`CI=true`。
4. **零僵尸容器保障（Zero Zombie Containers）**：
   - 无论脚本成功、失败、超时被杀或发生运行时异常，`finally` 块均强制执行 `container.remove(force=True)` 进行彻底清理。
5. **克制的功能边界**：
   - 本工具专注于验证脚本在基础 Linux 系统环境下的可执行性、命令可用性及返回码，不模拟 systemd、复杂 cgroups 或网络防火墙等重型系统环境。

---

## 🗂️ 默认测试矩阵（Default Matrix）

- `debian:12-slim`
- `ubuntu:22.04`
- `ubuntu:24.04`
- `alpine:3.20`

---

## 🚀 快速上手 (Quick Start)

### 1. 本地安装

要求 Python >= 3.10，宿主机需运行 Docker 服务：

```bash
git clone https://github.com/your-org/opsscript-gate.git
cd opsscript-gate
pip install .
```

### 2. CLI 命令行使用

```bash
# 基本运行（使用默认 4 镜像矩阵与 60s 超时）
opsscript-gate run ./deploy.sh

# 自定义矩阵、超时与输出格式
opsscript-gate run ./deploy.sh \
  --matrix "debian:12-slim,alpine:3.20" \
  --timeout 30 \
  --format table
```

#### CLI 参数说明：

- `script_path`（必填）：要预演验证的 Shell 脚本路径。
- `--matrix`（可选）：指定测试的 Docker 镜像列表，多个镜像以逗号分隔或重复指定。默认为 4 款常用发行版。
- `--timeout`（可选）：单个发行版执行超时时间（秒），默认 60 秒。
- `--format`（可选）：报告输出格式，可选 `table`（默认终端 ASCII 表格）、`markdown`（Markdown 表格与折叠详情）、`json`（JSON 数据结构）。

#### 退出码规范：
- 所有发行版均验证通过（PASS）：退出码为 `0`。
- 任意一个发行版失败（FAIL）、超时（TIMED_OUT）或发生异常（ERROR）：退出码为 `1`。

---

## 🤖 GitHub Actions 集成

将 `opsscript-gate` 作为 Composite Action 引入您的 CI 流水线：

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
        uses: ./
        with:
          script-path: 'scripts/setup.sh'
          matrix: 'debian:12-slim,ubuntu:22.04,ubuntu:24.04,alpine:3.20'
          timeout: '60'
          format: 'table'
```

当运行在 GitHub Actions 环境中时，`opsscript-gate` 会自动检测 `$GITHUB_STEP_SUMMARY`，将 Markdown 诊断表格与日志折叠详情直接注入 Action Job 概览页面。

---

## 🧪 测试套件

项目包含完整的单元测试与集成测试：
- **Mock 单元测试**：全面模拟 Docker SDK 调用与边界生命周期，无需宿主机 Docker 服务即可秒级测试通过。
- **集成测试**：带 `@pytest.mark.integration` 标记，针对真实 Docker 镜像拉起并执行校验。

运行测试：
```bash
# 运行快速单元测试（包含 Mock）
pytest -m "not integration"

# 运行所有测试（需宿主机 Docker 已启动）
pytest
```

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 协议开源。
