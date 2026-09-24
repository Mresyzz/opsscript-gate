# OpsScript Gate：Shell 脚本跨发行版运行检查

[English](README.md) · [配置说明](docs/configuration.md) · [常见问题](docs/troubleshooting.md)

在 Debian、Ubuntu、Alpine 容器里实际运行 Shell 脚本，提前发现缺失命令、
Bash 依赖、包管理器假设和交互式阻塞。它与 ShellCheck 互补。

适合独立安装脚本、容器入口脚本和发布脚本。每次只挂载目标脚本，
不挂载整个仓库；依赖其他仓库文件的脚本需要现有项目测试配合。

## 试用本次 v0.5.0 更新

本次更新尚未发布到 PyPI／GitHub Release，请从本地源码安装：

```bash
pip install -e .
opsscript-gate run examples/basic/clean_setup.sh --dry-run
```

在你希望接入检查的仓库根目录执行：

```bash
opsscript-gate init
opsscript-gate run --dry-run
opsscript-gate run --format json --output reports/compatibility.json
```

`init` 生成配置和 GitHub 工作流，不覆盖已有文件。工作流引用 `v0.5.0`，
需待该版本发布后使用。预览不需要 Docker；真实运行需要 Python 3.10+
和可访问的 Linux Docker 引擎。

生成的配置默认排除 `tests/*`、`examples/*`，使用 Debian + Alpine，尊重
脚本 shebang，并关闭网络。请根据实际脚本审核配置；需要下载文件时启用
`--network bridge`。保留现有无配置行为：四个发行版、POSIX shell、bridge 网络。

## 本轮改进

- 运行前展示脚本、镜像和总容器执行次数。
- 本地与 GitHub Actions 共用 `.opsscript-gate.json`。
- 排除规则、发行版预设、扫描数量限制。
- 超过扫描上限明确报错，避免只测前 20 个却误以为全部通过。
- 报告保存为 JSON、Markdown 或文本，失败时同样保留结果。
- 自动发现跳过符号链接，并严格校验配置与执行参数。

返回码 `0` 表示全部通过，`1` 表示检查失败或发生错误。`--dry-run` 成功只表示
执行计划生成成功。容器不是不可信代码的安全沙箱。

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
