# opsscript-gate

> Linux 运维脚本跨发行版（Debian / Ubuntu / Alpine）兼容性预演门禁与 GitHub Action。

在 Shell 脚本合并到主分支或发版前，使用轻量、无特权的瞬态容器自动进行预演，拦截命令缺失（如 Alpine 缺失 apt/bash）、未捕获退出码、交互挂死以及换行符问题。

[GitHub 仓库](https://github.com/Mresyzz/opsscript-gate) · [版本发布](https://github.com/Mresyzz/opsscript-gate/releases)

---

## 解决的问题

运维 Shell 脚本在跨系统分发时经常遇到以下问题：

- **系统依赖与命令缺失**：在 Ubuntu 上写好的脚本直接包含 `apt-get`、`systemctl` 或 bash 专属语法，分发到 Alpine（默认 BusyBox sh，包管理器为 apk）后因命令不存在报 127 退出。
- **CI 流水线交互挂死**：脚本意外调用 `read -p` 或安装程序弹出交互确认，CI 没有标准输入一直挂起直至超时被杀。
- **CRLF 换行符假性报错**：在 Windows 环境检出或修改的脚本带有 `\r\n`，在 Linux 容器中执行报错 `\r: command not found`。
- **静默失败被漏过**：脚本未配置严格错误捕获，某些子步骤失败却因最后一条命令成功而返回 0，导致带病上线。

`opsscript-gate` 在完全隔离的轻量容器中预跑脚本，捕获返回码与最后 15 行错误日志，拦截不兼容变更。

---

## 运行效果

### 控制台输出 (ASCII Table)

```text
+--------------------+----------+-----------+------------+----------------------------------------------------+
| Distro             | Status   | Exit Code | Duration   | Details                                            |
+--------------------+----------+-----------+------------+----------------------------------------------------+
| debian:12-slim     | PASS     | 0         | 1.12s      | OK                                                 |
| ubuntu:22.04       | PASS     | 0         | 1.05s      | OK                                                 |
| ubuntu:24.04       | PASS     | 0         | 1.08s      | OK                                                 |
| alpine:3.20        | FAIL     | 127       | 0.42s      | Script failed with non-zero exit code: 127         |
+--------------------+----------+-----------+------------+----------------------------------------------------+
Total duration: 3.67s | Result: FAILED

============================================================
Failed Distributions - Output Snippets (last 15 lines):
============================================================

--- [alpine:3.20] (FAIL) ---
/tmp/target_script.sh: line 5: apt-get: not found
```

### GitHub Actions 摘要 (Step Summary)

如果检测到环境变量 `$GITHUB_STEP_SUMMARY`，会自动将 Markdown 格式结果与失败折叠日志直接注入到 Action 执行页：

| Distro | Status | Exit Code | Duration | Message |
| :--- | :---: | :---: | :---: | :--- |
| `debian:12-slim` | ✅ PASS | `0` | `1.12s` | - |
| `ubuntu:22.04` | ✅ PASS | `0` | `1.05s` | - |
| `ubuntu:24.04` | ✅ PASS | `0` | `1.08s` | - |
| `alpine:3.20` | ❌ FAIL | `127` | `0.42s` | Script failed with non-zero exit code: 127 |

---

## 隔离与安全设计

1. **绝对无特权容器**：
   - 严禁 `--privileged`，剥离所有 Linux Capability（`cap_drop=["ALL"]`）。
   - 禁止挂载宿主机敏感目录（如 `/var/run/docker.sock`）。
2. **只读挂载**：
   - 宿主机待测脚本以只读模式挂载至容器内（`{"bind": "/tmp/target_script.sh", "mode": "ro"}`）。
3. **彻底防挂死**：
   - 显式关闭标准输入与 TTY（`stdin_open=False`, `tty=False`）。
   - 执行命令强制重定向：`/bin/sh -c "/bin/sh /tmp/target_script.sh </dev/null"`。
   - 注入非交互环境变量：`DEBIAN_FRONTEND=noninteractive`、`CI=true`。
4. **硬超时中断**：
   - 默认每个发行版 60 秒硬超时，超时后显式调用 `container.kill()`，标记状态为 `TIMED_OUT`。
5. **资源回收保底**：
   - 无论脚本成功、失败、超时被强杀或抛出 Python 异常，`finally` 块一律执行 `container.remove(force=True)`。
6. **换行符防御**：
   - 自动检测并临时将 CRLF (`\r\n`) 转换为 LF (`\n`)，避免 Windows 换行符污染。
7. **POSIX sh 红线**：
   - 容器内严格使用 `/bin/sh`，不依赖 `/bin/bash`，确保 Alpine 容器正常执行。

---

## 默认测试矩阵

- `debian:12-slim`
- `ubuntu:22.04`
- `ubuntu:24.04`
- `alpine:3.20`

---

## 快速上手

### 本地命令行

环境要求：Python >= 3.10，宿主机安装并启动 Docker。

```bash
# 从仓库安装
pip install git+https://github.com/Mresyzz/opsscript-gate.git

# 基本使用（默认使用 4 个发行版矩阵）
opsscript-gate run ./scripts/setup.sh

# 自定义测试矩阵与超时时间
opsscript-gate run ./scripts/setup.sh \
  --matrix "debian:12-slim,alpine:3.20" \
  --timeout 30 \
  --format table
```

### GitHub Actions 集成

在工作流文件（如 `.github/workflows/gate.yml`）中引入：

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
| `script_path` | 路径 (位置参数) | 必填 | 要预演验证的 Shell 脚本路径 |
| `--matrix` | 字符串 | 4 个默认镜像 | 逗号分隔的容器镜像列表（如 `debian:12-slim,alpine:3.20`） |
| `--timeout` | 整数 | `60` | 单个镜像最大执行时间（秒） |
| `--format` | 选项 | `table` | 报告输出格式：`table`（终端对齐表格）、`markdown`、`json` |
| `--version` | 标志 | - | 显示当前版本号 |
| `-h, --help` | 标志 | - | 查看参数帮助信息 |

#### 退出状态码：
- **`0`**：所有指定发行版均验证通过（PASS）。
- **`1`**：任一发行版失败（FAIL）、超时（TIMED_OUT）或发生异常（ERROR）。

---

## 开发与本地测试

测试套件已实现纯 Mock 隔离，无需启动 Docker 即可秒级执行：

```bash
# 安装开发与测试依赖
pip install -e .[test]

# 运行 Mock 单元测试
pytest -v -m "not integration"

# 运行全部测试（包含真实容器集成测试，需启动 Docker）
pytest -v
```

---

## 开源协议

本项目采用 [MIT License](LICENSE) 协议开源。
