# CLAUDE.md

本文件为在 `E:\CCProject\agent_reach` 中工作的 Claude Code 提供项目指引。

## 仓库概览

Agent Reach 是一个 Windows 优先、**完全项目内隔离**的 Python CLI。它为渠道适配器提供诊断、更新检查、项目托管安装与 skill 刷新能力。第一期仅完整接入 OpenCLI；其他渠道通过可扩展 adapter registry 预留接口。

## 核心约束

- 所有 Agent Reach 的依赖、运行时、配置、缓存、日志、临时文件、技能和项目托管工具必须位于 `E:\CCProject\agent_reach` 内。
- 项目内虚拟环境固定为 `.venv\`；运行态固定为 `runtime\`；项目托管工具固定为 `tools\` 或 `runtime\tools\`。
- 不得默认使用或创建 `%USERPROFILE%\.agent-reach`、`~/.agent-reach`、系统临时目录、用户/系统 PATH、全局 pip/pipx 环境、注册表或 Program Files 中的文件。
- 所有外部子进程必须使用参数数组和 `shell=False`；通过 `RuntimePaths.child_environment()` 将 `HOME`、`USERPROFILE`、`TMP`、`TEMP`、`TMPDIR`、`XDG_*` 映射到项目内目录。
- 所有写入都必须经 `ensure_within_project()` 验证，防止绝对路径、路径穿越和 symlink/junction 逃逸。
- 不得卸载用户已有工具。对项目托管工具仅可在明确检测到既有登记项后升级；未登记工具应输出人工操作说明，而非自动全局安装。

## OpenCLI 安全与交互边界

- `agent-reach install --system --channels opencli` 中的 `--system` 仅为上游兼容参数，必须映射为 **project-managed** 模式，绝不执行系统级安装。
- 不自动安装/启用浏览器扩展，不控制浏览器，不自动登录。
- 不读取 Cookie、浏览器 profile、密码库、浏览器 SQLite 数据库或任何认证数据库。
- 浏览器扩展和登录问题必须以 `manual_action_required` 报告，并给出用户可执行的明确人工步骤。
- `doctor --json` 的 stdout 必须是严格 JSON，始终包含 `active_backend`，每个非健康项都必须附带精确的 `fix`；日志和进度信息写入 stderr。

## 代码组织

- `pyproject.toml` — 打包、console script、依赖和 pytest 配置。
- `main.py` — 兼容入口，转发到 `agent_reach.cli:main`。
- `src/agent_reach/paths.py` — 项目根发现、运行时目录和路径安全边界的唯一来源。
- `src/agent_reach/cli.py` — CLI 命令注册与退出码。
- `src/agent_reach/doctor.py` — 文本/JSON 诊断编排。
- `src/agent_reach/update.py` — 仅检查更新，不负责升级。
- `src/agent_reach/installer.py`、`skill.py` — 仅处理项目内受管理资源。
- `src/agent_reach/channels/` — 渠道适配器；`opencli.py` 是第一期实现。
- `src/agent_reach/backends/` — 后端协议、注册与 `active_backend` 选择。
- `tests/` — pytest 测试。网络和外部进程必须 mock；不得在测试中触碰真实浏览器或全局环境。
- `.idea/` — PyCharm 元数据；除非确有必要，否则不要改动。

## 开发命令

以下命令必须在项目根运行，且所有安装操作使用项目内虚拟环境：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m py_compile main.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\agent-reach.exe version
.\.venv\Scripts\agent-reach.exe doctor --offline --json
.\.venv\Scripts\agent-reach.exe install --system --channels opencli --dry-run
.\.venv\Scripts\agent-reach.exe skill --install --dry-run
```

## 回复语言

默认使用中文汇报计划、修改、测试结果和错误信息，除非用户明确要求其他语言。
