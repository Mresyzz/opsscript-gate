# OpsScript Gate：GitHub Action 跨发行版 Shell 安装脚本测试

[English](README.md) · [配置说明](docs/configuration.md) · [常见问题](docs/troubleshooting.md) · [自托管模型安装脚本指南](docs/gpt-oss.md)

在 Debian、Ubuntu、Alpine 容器里实际运行 Shell 脚本，提前发现缺失命令、
Bash 依赖、包管理器假设和交互式阻塞。它与 ShellCheck 互补。

适合独立安装脚本、容器入口脚本和发布脚本。每次只挂载目标脚本，
不挂载整个仓库；依赖其他仓库文件的脚本需要现有项目测试配合。

也可以直接打开 [OpsScript Gate 在线演示](https://mresyzz.github.io/opsscript-gate/)，先查看 ShellCheck 与运行时验证的差异，再复制 workflow 到自己的仓库。

## 当前版本 v0.8.2

v0.8.2 已作为正式版本发布；如果你要从源码验证当前分支，也可以执行：

```bash
pip install -e .
opsscript-gate run examples/basic/clean_setup.sh --dry-run
```

在你希望接入检查的仓库根目录执行：

```bash
opsscript-gate init
opsscript-gate doctor
opsscript-gate run --dry-run
opsscript-gate run --format json --output reports/compatibility.json
```

`init` 生成配置和 GitHub 工作流，不覆盖已有文件。工作流引用 `v0.8.2`。
预览不需要 Docker；真实运行需要 Python 3.10+
和可访问的 Linux Docker 引擎。
`opsscript-gate doctor` 可以在真实运行前检查 Python 和 Docker。

需要接入 GitHub Code Scanning 时，将 `--format sarif --output reports/opsscript-gate.sarif`
传给运行命令，再用 `github/codeql-action/upload-sarif@v3` 上传报告。每个失败发行版
都会保留脚本路径、诊断行号、命令和退出码；全部通过时仍会生成合法的空 SARIF 报告。

生成的配置默认排除 `tests/*`、`examples/*`，使用 Debian + Alpine，尊重
脚本 shebang，并关闭网络。请根据实际脚本审核配置；需要下载文件时启用
`--network bridge`。安装器如果需要 `curl`、证书或其他明确工具，可以配置
`packages`；运行器会用镜像自带的 `apt-get` 或 `apk` 安装它们。包安装是可选的，
只接受包名，不接受 Shell 命令，并且必须使用 `bridge` 网络。保留现有无配置行为：
四个发行版、POSIX shell、bridge 网络。

## 本轮改进

- 运行前展示脚本、镜像和总容器执行次数。
- 本地与 GitHub Actions 共用 `.opsscript-gate.json`。
- 排除规则、发行版预设、扫描数量限制。
- 超过扫描上限明确报错，避免只测前 20 个却误以为全部通过。
- 报告保存为 JSON、Markdown 或文本，失败时同样保留结果。
- 自动发现跳过符号链接，并严格校验配置与执行参数。

返回码 `0` 表示全部通过，`1` 表示检查失败或发生错误。`--dry-run` 成功只表示
执行计划生成成功。容器不是不可信代码的安全沙箱。

需要排查本地环境时运行 `opsscript-gate doctor --format json`；它会检查 Python、
Docker daemon 和可选的项目配置。

在 Pull Request 中只检查本次修改的脚本，可以先获取完整 Git 历史，再传入目标分支提交：

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0
- uses: Mresyzz/opsscript-gate@v0.8.2
  with:
    changed-since: ${{ github.event.pull_request.base.sha }}
    preset: minimal
```

如果本次修改没有 Shell 脚本，检查会直接通过，不启动容器。 本地可以用
`opsscript-gate run --changed-since origin/main --dry-run` 预览选择结果。

如果仓库维护自托管模型的安装或启动脚本，可以参考
[自托管模型安装脚本指南](docs/gpt-oss.md)。它只验证 Shell 和发行版兼容性，
不代替 GPU、模型权重或推理质量测试。

## 示例：为什么 Alpine 上会失败

```sh
#!/bin/sh
set -e
apt-get --version
```

这个脚本可以符合 POSIX 语法，但 Alpine 使用 `apk`，实际执行会暴露命令缺失。
查看 [Ubuntu／Alpine 排错说明](docs/troubleshooting.md) 获取常见原因与修复方向。

## 测试

```bash
pip install -e '.[test]'
pytest -q -m 'not integration'
pytest -q -m integration
```

第二组需要 Docker。跳过容器测试不能算作完整集成验证。
