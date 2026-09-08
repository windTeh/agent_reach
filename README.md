# Agent Reach

一个 Windows 优先、完全项目内隔离的 Python CLI，用于检查和维护 Agent Reach 渠道适配器。

> **第一期范围：** 完整实现 OpenCLI 的诊断与项目托管维护框架；Twitter、Bilibili、小红书、YouTube、RDT 与 mcporter 仅预留扩展接口。

## 隔离保证

Agent Reach 不会默认写入用户主目录、系统临时目录、全局 Python/npm 环境或系统 PATH。运行时资源固定在本项目中：

| 类型 | 位置 |
| --- | --- |
| 虚拟环境 | `.venv\` |
| 配置、状态、缓存、日志、临时文件 | `runtime\` |
| 项目托管工具 | `tools\`、`runtime\tools\` |
| 项目托管 skill | `tools\skills\` |

`install --system` 是上游命令兼容参数；它在本项目中只会映射为 **project-managed** 模式，绝不会修改 Windows 系统/用户 PATH、注册表、Program Files 或全局 pip/npm/pipx。

## 安装（仅项目内）

在 `E:\CCProject\agent_reach` 的 PowerShell 中执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

如果 `py` 不可用，请将上面的 `py` 改为 `python`。

## 常用命令

```powershell
# 版本
.\.venv\Scripts\agent-reach.exe version
.\.venv\Scripts\agent-reach.exe --version

# 诊断
.\.venv\Scripts\agent-reach.exe doctor
.\.venv\Scripts\agent-reach.exe doctor --json

# 仅检查 Agent Reach 更新；不会下载或升级任何内容
.\.venv\Scripts\agent-reach.exe check-update
.\.venv\Scripts\agent-reach.exe check-update --offline

# 查看 OpenCLI 的项目内维护计划；不会执行安装
.\.venv\Scripts\agent-reach.exe install --system --channels opencli --dry-run

# 刷新项目内受管理 skill；演练模式不会写文件
.\.venv\Scripts\agent-reach.exe skill --install --dry-run
```

也可在开发环境执行：

```powershell
.\.venv\Scripts\python.exe main.py doctor --json
.\.venv\Scripts\python.exe -m agent_reach doctor --json
```

## OpenCLI 的人工步骤

Agent Reach **不会**：

- 安装、启用或操控浏览器扩展；
- 自动登录；
- 读取 Cookie、Chrome profile、浏览器数据库、密码库或其他认证存储；
- 将 OpenCLI 安装到全局 npm/Python/PATH 环境。

如果 `doctor` 提示 OpenCLI 扩展或登录需要操作，请你自行在浏览器完成：

1. 在浏览器扩展商店安装或启用 OpenCLI 扩展；
2. 需要时自行完成登录；
3. 回到项目根目录重新运行 `agent-reach doctor`。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py
.\.venv\Scripts\python.exe -m pytest -q
```

测试会 mock 网络与子进程，不会连接真实浏览器、读取浏览器数据或执行全局安装。
