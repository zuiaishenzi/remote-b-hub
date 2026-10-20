# Remote B Hub

新增 **A/B 桌面端“检查更新”**：从 GitHub 稳定 Release 下载、核对 SHA256、隔离自检，
退出后替换并重启，保留已保存的 Token、模板和路径。旧版需首次手动更新一次，以后可在程序内更新。
同时新增 **AngelSix / SolidDNA 的 SW2023 Interop 技能适配**与受限尺寸读取；不是直接运行整个上游 SDK。
详见 [更新按钮、技能集成与验证边界](docs/desktop-updates.md)。

2026-10-20：新增 **SolidWorks 2023 建模技能**，集成到 A 端 EXE 和 pc-b MCP。
更新后点击 A 控制台“建模技能”，可生成带参数校验的严格配方、提交任务并复核真实结果；
点击“安装到工作目录”后重启 Codex，即可发现两项项目技能。
实机已保存长方体、圆柱、偏心圆及修订后的圆管；双孔板验收失败，已禁止模板自动提交。
这不代表精确齿轮、装配或运动学已完成。详见
[技能来源、安装与实机验收记录](docs/solidworks-skills.md)。

本次升级：新增 A 桌面控制台、受限 PowerShell/C# Interop 文档控制、鉴权截图附件，
并修复 B EXE 无法直接关闭的问题。新版“×”一次退出启动器并请求代理完成当前任务后停止；
驻留使用独立的“最小化驻留”按钮。
详见 [升级顺序、实际能力及图片/视频手动配置](docs/script-control-upgrade.md)。
需要同时更新 NAS、A 桥接与 B EXE；新版文件见 [Releases](https://github.com/zuiaishenzi/remote-b-hub/releases/latest)。

实时观看 B 的画面：参见 [绿联 NAS 自建 RustDesk：Docker、FRP 与 A/B 配置](docs/rustdesk-ugreen-nas.md)。
该方案作为独立远程桌面通道部署；模型看图继续使用项目的鉴权截图工具。

偏离原点的圆在 `FullyDefineSketch` 报“类型不匹配”时，参见
[基准参数 COM 修复、执行器版本识别与偏心圆回归](docs/fully-define-com-fix.md)。
修复需更新 B 实际运行的 EXE；源码拉取不会热更新 EXE。

Windows B 桌面版：使用 `RemoteBHub.exe` 配置 Token、模板和输出目录，检查/启动
SOLIDWORKS 与任务代理，查看日志，并支持登录驻留、代理自动重启及 CAD 任务按需启动 SW。
详见 [桌面启动器使用与自动启动边界](docs/desktop-launcher.md)。本地构建双击 `build-desktop.bat`。

首次配置请先阅读 [如何获取和配置 A / B 的 Token](#如何获取和配置-a--b-的-token)。

双击根目录的 `upload-github.bat`，会先检查 Python 语法并运行 COM 回归测试，
然后提交全部未被 `.gitignore` 排除的改动并推送到 `origin` 的当前分支。
首次使用需安装 Git for Windows、Python（含 `py` 启动器）并完成 GitHub 登录；
Git 提交身份需已配置。失败时窗口会保留错误，已有本地提交也会保留。
其他设备使用 `git pull --ff-only` 更新，Windows B 更新 Python 后需重启原代理。

> SOLIDWORKS 草图选择报“无法读只写属性 / 找不到成员”时，参见
> [COM 选择修复与 Windows B 验证步骤](docs/selection-com-fix.md)。
> 本地回归测试已通过，目标工作站的实机选择及严格建模仍需分阶段验收。

2026-10-19 Windows B 已实机验证选择管理器和矩形边/圆的 `Select2` 选择。
下一步运行 `py -3 .\windows-b\probe_parametric_part.py --profile rectangle`，
通过后再测试 `--profile circle`，详见上述验证文档。测试会创建并按严格检查结果保存全新零件。

> 通过一台 Debian Linux 服务器，将 **电脑 A 上的 Codex** 与 **电脑 B 上的 Windows 应用**连接起来。电脑 B 无需访问 OpenAI，也无需拥有公网 IP。

**当前阶段：MVP（最小可用原型）**。本仓库提供 Linux 任务中转服务、Windows B 任务执行代理、Windows A 的 Codex MCP 桥接程序和安装脚本。第一阶段用于验证远程通信及 SolidWorks COM 调用基础能力，**不是**成熟的通用远程桌面或完整 SolidWorks 自动建模软件。

## 1. 项目目标

本项目的目标是让低性能的 **电脑 A** 负责与 Codex 交互，将任务交给性能较强但无法访问 OpenAI 的 **电脑 B** 执行。后续可扩展 SolidWorks 2023、Python、MATLAB 及其他 Windows 应用。

- 电脑 A：运行 Codex，提交任务、查询执行状态及结果。
- Debian 服务器：统一对外入口、鉴权、任务队列、任务记录与结果中转。
- 电脑 B：主动连接服务器领取任务，在本机执行白名单操作并回传结果。
- FRP 与域名 B：用户已有的内网穿透能力；本仓库 **不自动部署或修改 FRP**。

### 系统架构

```text
                       HTTPS（经域名 B / 用户自建 FRP）
 Windows 电脑 A  -------------------------------------------+
 Codex CLI                                                 |
   └─ stdio MCP bridge (windows-a/mcp_bridge.py)            |
       └─ REST API /api/*                                   |
                                                            v
                                         Debian 12 ARM64 Linux 服务器
                                         FastAPI + SQLite + systemd
                                         127.0.0.1:18765（仅本机）
                                                            ^
                                                            |
 Windows 电脑 B --------------------------------------------+
 Windows Agent (windows-b/agent.py)     HTTPS（主动轮询 /agent/*）
   ├─ ping / system_info
   └─ SolidWorks 2023 COM（需要同一登录用户会话）
```

> **为什么不直接用 UU 远程或 Tailscale？** FRP、Tailscale、UU 远程主要解决连通性或画面传输；MCP/执行代理解决“Codex 可以调用哪些操作”。本项目选择**服务器中转 + 电脑 B 主动轮询**，不需要打开电脑 B 的入站端口，也不依赖电脑 A 的前台远程窗口。

## 2. 当前实现情况（请先阅读）

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| Linux FastAPI 服务 | 已编写 | 默认监听 `127.0.0.1:18765` |
| 分别为 A/B 鉴权 | 已编写 | 独立 Bearer Token，需本地生成 |
| SQLite 任务队列与结果查询 | 已编写 | 单代理 MVP，状态为 `queued/running/done/error/interrupted` |
| Windows B 主动轮询 | 已编写 | 从服务器取白名单任务并回传结果 |
| Windows A stdio MCP 桥接 | 已编写 | 把 Codex 工具调用转换为 REST 请求 |
| `ping`、`system_info` | 已编写 | 无需 SolidWorks，可用于端到端验证 |
| `solidworks_status` | 已编写 | 查询当前用户会话中的 SolidWorks COM |
| `create_blank_part` | 已编写，待实机验证 | 基于 `.prtdot` 创建**空白** SLDPRT，不做几何建模 |
| SolidWorks 参数化特征/装配建模 | 已有受限 recipe | 严格草图、拉伸/切除、插入零件及基本配合；装配仍需实机验收 |
| PowerShell/C# Interop 文档控制 | 新增，待 B 验收 | 装配树、几何摘要、只读打开、重建、保存副本、安全关闭 |
| SW 窗口诊断截图 | 新增，待 B 采集验收 | B 本地启用，NAS 独立鉴权附件，A 下载/打开 |
| 实时视频、鼠标键盘/Computer Use | **未实现** | 视频需另行手动配置 |
| 任意 PowerShell / 启停任意应用 | **未开放** | 当前采用严格操作白名单 |
| 用户 Debian、FRP、电脑 A/B 实机部署 | **尚未完成** | 需要依照以下步骤逐项验证 |

**验证口径：**仓库提供本地 HTTP 队列测试与模拟代理的集成测试，不能代替 Debian ARM64、真实 FRP 网络、Codex CLI 或 SolidWorks 2023 实机测试。不要把“代码已编写”误认为“环境已部署成功”。

## 3. 项目目录

```text
remote-b-hub/
├── README.md
├── .gitignore
├── scripts/
│   └── install-debian12.sh        # Debian 12 安装脚本
├── linux-server/
│   ├── server.py                  # FastAPI 中转服务
│   ├── requirements.txt
│   ├── hub.env.example            # 环境变量示例：严禁填入真实密钥后提交
│   ├── remote-b-hub.service       # systemd 服务
│   └── nginx-https-example.conf  # 可选 HTTPS 反向代理示例
├── windows-b/
│   └── agent.py                   # 电脑 B 主动领取任务并执行
├── windows-a/
│   ├── mcp_bridge.py              # Codex stdio MCP 适配器
│   └── requirements.txt
└── tests/
    ├── smoke_test.py
    └── e2e_http_test.py
```

## 4. 已知服务器环境与统一参数

目前确认的 Linux 服务器环境（不是安装成功的证明）：

| 项目 | 已确定值 |
| --- | --- |
| 系统 | Debian 12.8 |
| 架构 | ARM64 / `arm64` |
| Python | 3.11.2 |
| 中转端口 | `18765/TCP` |
| 服务器内部地址 | `http://127.0.0.1:18765` |
| 公网入口 | `https://域名B`，由使用者自行配置 |
| 服务器代码 | `/opt/remote-b-hub` |
| 服务器本地密钥文件 | `/etc/remote-b-hub/hub.env` |
| systemd 服务名称 | `remote-b-hub` |

此处“域名 B”只是占位符，不应写入真实私有域名或令牌再公开提交。

## 5. 第一步：部署 Debian 12 ARM64 服务器

**先确认 GitHub 仓库已经包含本项目文件。** 新建的空仓库直接 `git clone` 不能执行后续脚本；应先上传源码。下述命令需要 root 权限。

```bash
apt update && apt install -y git
cd /opt
git clone https://github.com/zuiaishenzi/remote-b-hub.git remote-b-hub-source
cd /opt/remote-b-hub-source
bash scripts/install-debian12.sh
```

安装脚本将：

1. 安装 `python3`、`python3-venv`、`python3-pip` 等依赖。
2. 创建低权限账号 `remotebhub`。
3. 将服务文件复制到 `/opt/remote-b-hub` 并创建 Python 虚拟环境。
4. 首次部署时用 `openssl` 生成互不相同的 64 位十六进制字符串 `HUB_A_TOKEN` 与 `HUB_B_TOKEN`。
5. 将真实配置保存到 **仅 root 可读取** 的 `/etc/remote-b-hub/hub.env`，不会写回公开仓库。
6. 安装并启动 `remote-b-hub.service`，只监听本机 `127.0.0.1:18765`。

服务器检查：

```bash
systemctl status remote-b-hub --no-pager
curl -fsS http://127.0.0.1:18765/health
ss -lntp | grep 18765
```

预期健康检查结果：

```json
{"status":"ok","service":"pc-b-relay"}
```

查看失败原因：

```bash
journalctl -u remote-b-hub -n 80 --no-pager
```

### 统一在服务器修改配置

```bash
nano /etc/remote-b-hub/hub.env
systemctl restart remote-b-hub
```

```ini
HUB_A_TOKEN=<服务器生成的电脑A令牌>
HUB_B_TOKEN=<服务器生成的电脑B令牌>
HUB_DB=/opt/remote-b-hub/jobs.sqlite3
```

**不要把 `hub.env`、token、SSH 私钥或真实 CAD 文件提交到 GitHub，也不要把它们贴到聊天中。** 电脑 A/B 运行时需要分别使用自己对应的令牌，令牌本身不能只保存在服务器而不分发给客户端。

### 如何获取和配置 A / B 的 Token

**两枚 Token 均由 NAS 首次安装脚本生成，保存在 NAS 的
`/etc/remote-b-hub/hub.env` 中。** 它们不是 GitHub Token，也不需要从 OpenAI 获取。
重复运行安装脚本会保留已有配置，不应为了获取 Token 而重新生成或覆盖文件。

在 **NAS 的 SSH 终端**中分别执行以下只读命令（需要 root 或 sudo 权限）：

```bash
# 电脑 A 使用：读取 HUB_A_TOKEN
sudo grep '^HUB_A_TOKEN=' /etc/remote-b-hub/hub.env

# 电脑 B 使用：读取 HUB_B_TOKEN
sudo grep '^HUB_B_TOKEN=' /etc/remote-b-hub/hub.env
```

如果已经是 root，可省略 `sudo`。输出为 `变量名=实际值`，**仅复制等号后面的值**，
不要复制变量名、等号、空格或换行。命令会在当前终端显示真实密钥，不要将输出截图、
粘贴到聊天、日志或 GitHub。如果提示文件不存在，先完成第 5 节的 NAS 首次部署；
仓库 `hub.env.example` 中的占位符不能用作真实 Token。

| 获取来源（NAS） | 使用设备 | 填写位置 |
| --- | --- | --- |
| `HUB_A_TOKEN` 的值 | 电脑 A | `REMOTE_B_CLIENT_TOKEN` 环境变量，供 MCP 桥接使用 |
| `HUB_B_TOKEN` 的值 | 电脑 B | EXE 中的 **B Token / HUB_B_TOKEN**；命令行代理使用 `REMOTE_B_AGENT_TOKEN` |

**电脑 A：**在启动 Codex CLI 的同一个 PowerShell 窗口中输入：

```powershell
$env:REMOTE_B_API_URL = 'https://你的NAS服务入口'
$aTokenSecure = Read-Host '粘贴 NAS 的 HUB_A_TOKEN 值' -AsSecureString
$env:REMOTE_B_CLIENT_TOKEN = [System.Net.NetworkCredential]::new('', $aTokenSecure).Password
Remove-Variable aTokenSecure
codex
```

输入时不显示 Token。MCP 桥接需已按第 8 节注册；该配置只对当前窗口及其子进程有效。
如果 Codex 已在别的窗口运行，需要在这个配置好环境的窗口中重新启动，使桥接进程读取新值。

**电脑 B（推荐 EXE）：**打开 `RemoteBHub.exe`，在 NAS 地址中填写服务入口，
将 `HUB_B_TOKEN` 的值粘贴到 **B Token / HUB_B_TOKEN**，点击“保存设置”，再“启动代理”。
Token 会按当前 Windows 用户加密保存在本机；代理显示 `idle` 表示已成功鉴权并轮询 NAS。
仅 NAS 健康检查成功不能证明 Token 正确。

**电脑 B（仍用命令行代理时）：**在启动代理的同一个 PowerShell 中设置：

```powershell
$env:REMOTE_B_SERVER_URL = 'https://你的NAS服务入口'
$bTokenSecure = Read-Host '粘贴 NAS 的 HUB_B_TOKEN 值' -AsSecureString
$env:REMOTE_B_AGENT_TOKEN = [System.Net.NetworkCredential]::new('', $bTokenSecure).Password
Remove-Variable bTokenSecure
py -3 .\windows-b\diagnostic_agent.py
```

命令行方式还需按第 7 节配置模板和输出目录；不要与 EXE 的代理同时运行。
出现 `401 Unauthorized` 时，先核对 A/B 是否填反、复制是否完整，以及代理/桥接是否仍在
使用旧环境值。若主动修改了 NAS 的 Token，需同步更新对应客户端并重启 NAS 服务加载新值；
**仅查看和复制现有 Token 不需要重启 NAS。**

## 6. 第二步：自行配置 FRP 与域名 B

这一阶段由使用者自行部署，项目**不会**修改现有的 FRP 服务及站点。

要求：

- 公网访问 `https://域名B`，使用有效 TLS 证书。
- 公网 HTTPS 请求由已有 FRP/反向代理转发至 Debian 服务器的 `http://127.0.0.1:18765`。
- 转发时**保留 `Authorization` 请求头**，允许 GET/POST 请求和 JSON 响应。
- 不要将 `127.0.0.1:18765` 的明文 HTTP 端口直接映射为对公网开放的 TCP HTTP 接口。
- 假设 FRP 客户端和中转程序运行在**同一台 Debian 服务器**；若不是，需要调整监听地址和访问策略，不能照搬 `127.0.0.1`。

公网检测（可从电脑 A 访问）：

```text
https://域名B/health
```

应该返回与本地相同的 JSON。健康检查成功只证明 HTTP 连通，不代表 Token、代理或 SolidWorks 已通过测试。

如果电脑 B 所在网络无法解析或访问 `https://域名B`，需另外提供一条**受保护**的局域网/内网入口；MVP 默认监听回环地址，电脑 B 不能直接访问服务器的 `192.168.x.x:18765`。

## 7. 第三步：配置 Windows 电脑 B

电脑 B 是实际执行端，不需要登录 Codex 或连接 OpenAI。安装 Python 3.11+，从仓库获取 `windows-b/agent.py`，放到 `C:\RemoteB\agent.py`。

在 PowerShell 中测试：

```powershell
cd C:\RemoteB
$env:REMOTE_B_SERVER_URL = 'https://域名B'
$env:REMOTE_B_AGENT_TOKEN = Read-Host '请输入 Debian 中的 HUB_B_TOKEN'
py .\agent.py
```

- 这会持续轮询服务器并领取任务。**第一次先只测试 `ping` 和 `system_info`**。
- PowerShell 环境变量对当前窗口及其子进程有效，关闭窗口后需要重新设置。
- 令牌属于电脑 B，不能与电脑 A 的令牌混用。

### 若要测试 SolidWorks 2023

```powershell
py -m pip install pywin32
$env:REMOTE_B_OUTPUT_DIR = 'C:\RemoteB\output'
$env:REMOTE_B_PART_TEMPLATE = 'C:\实际模板路径\Part.prtdot'
```

上述 `REMOTE_B_OUTPUT_DIR` 和 `REMOTE_B_PART_TEMPLATE` 变量必须在**启动代理之前设置**（修改后重启代理）。请将示例 `.prtdot` 路径换成实际零件模板。

先在电脑 B 用当前 Windows 用户正常启动 SolidWorks，再用**同一登录用户的交互式会话**运行 `agent.py`。不建议以 `SYSTEM` 服务或 Session 0 执行 SolidWorks COM/GUI 自动化。电脑 B 的 SolidWorks 许可证、模板、保存路径和读写权限必须正常。

`create_blank_part(name)` 目前仅新建空白零件，文件名只允许 1–50 个英文字母、数字、`_`、`-`，且拒绝覆盖已有文件。

## 8. 第四步：配置 Windows 电脑 A（Codex）

电脑 A 运行 Codex CLI，并通过本地 stdio MCP 桥接程序把工具调用转发至 Linux 服务器的 HTTP API。
安装 Python 3.11+ 和 Git，保留完整仓库目录；新版桥接还依赖建模技能模块与 `.agents/skills`，不要只复制一个 Python 文件。

在 PowerShell 中执行：

```powershell
git clone https://github.com/zuiaishenzi/remote-b-hub.git C:\RemoteB\remote-b-hub
cd C:\RemoteB\remote-b-hub
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r windows-a/requirements.txt

$env:REMOTE_B_API_URL = 'https://域名B'
$env:REMOTE_B_CLIENT_TOKEN = Read-Host '请输入 Debian 中的 HUB_A_TOKEN'

codex mcp add pc-b -- C:\RemoteB\remote-b-hub\.venv\Scripts\python.exe C:\RemoteB\remote-b-hub\windows-a\mcp_bridge.py
codex mcp list
codex
```

**注意：**必须在设置环境变量的同一个 PowerShell 会话中启动 Codex，使它的 MCP 子进程能够读取上述变量。若从桌面快捷方式启动 Codex，可能无法继承终端中的环境变量，需要另外配置安全的持久化凭据注入方式。本项目当前针对 **Codex CLI**，尚未验证各桌面应用的 MCP 配置入口。

已存在该仓库时使用 `git pull --ff-only`，不必重新克隆。MCP 注册方法参见
[OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。
项目技能加载位置参见 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

建议的第一条任务：

```text
使用 pc-b MCP 工具，先运行 computer_b_status。
然后调用 computer_b_ping，记录返回的 job_id。
使用 computer_b_job(job_id) 查询，直至任务完成。
不要在电脑 A 上模拟电脑 B 的执行结果，也不要执行 SolidWorks 建模。
```

之后再测试 `computer_b_system_info`、`computer_b_solidworks_status` 和 `computer_b_create_blank_part`。

## 9. 已实现的接口和 MCP 工具

| API | 方法 | 谁可以调用 | 用途 |
| --- | --- | --- | --- |
| `/health` | GET | 无需令牌 | 健康检查 |
| `/api/status` | GET | A Token | 查询 B 最近在线状态及待处理任务数 |
| `/api/jobs` | POST | A Token | 创建白名单任务 |
| `/api/jobs/{job_id}` | GET | A Token | 查询状态、结果与错误 |
| `/agent/next` | GET | B Token | 领取任务、更新心跳 |
| `/agent/jobs/{job_id}/result` | POST | B Token | 回传任务结果 |

| Codex MCP 工具 | 用途 |
| --- | --- |
| `computer_b_status` | 检查 B 的在线状态 |
| `computer_b_ping` | 领取队列中的无害测试任务 |
| `computer_b_system_info` | 返回 B 的系统信息 |
| `computer_b_solidworks_status` | 检查 B 是否在当前会话运行 SolidWorks |
| `computer_b_create_blank_part(name)` | 新建空白零件，不覆盖已有文件 |
| `computer_b_job(job_id)` | 查询任务结果 |

MCP 桥接程序调用后通常**先返回 `job_id`**，不是同步等待 Windows 软件完成。Codex 应用 `computer_b_job` 继续查询直至返回 `done` 或 `error`；服务重启时，原先正在运行的任务可能显示为 `interrupted`，不会自动重新执行有副作用的建模动作。

## 10. 本地测试（开发环境）

可以先在装有相应 Python 库的环境中运行测试，无需电脑 B 或 SolidWorks：

```bash
python3 -m pip install -r linux-server/requirements.txt httpx
python3 tests/smoke_test.py
python3 tests/e2e_http_test.py
```

`smoke_test.py` 检查鉴权、任务入队/领取/返回结果及操作白名单；`e2e_http_test.py` 启动真实本地 HTTP 服务和模拟执行代理，测试 `ping` 任务闭环。均不等同于公网 FRP 或 SolidWorks COM 实机测试。

## 11. 安全边界

1. GitHub 公开仓库只能包含源码、文档和示例配置；实际令牌只放在安全的本地配置中。
2. Linux 服务默认仅监听 `127.0.0.1:18765`；公网入口必须由可信 HTTPS 反向代理保护，最好再限制可访问来源与频率。
3. 电脑 A 与 B 令牌独立；MVP 未实现令牌轮换 API、用户级权限管理、速率限制或完整审计。
4. 只允许四种操作：`ping`、`system_info`、`solidworks_status`、`create_blank_part`，不提供任意 PowerShell、任意文件写入或远程鼠标点击。
5. 服务器只负责转发和存储任务，**不在 Linux 上运行 SolidWorks**。
6. B 上的 COM/GUI 自动化需在合适的 Windows 交互式用户会话运行；锁屏、切换会话、UAC 弹窗和许可证问题均可能使操作失败。
7. 任务数据库、日志及返回内容可能包含主机名、文件路径等敏感信息，需按实际使用环境管理访问权限及保留期限。
8. 当前为单代理 MVP：没有多电脑调度、独立工作队列、多用户租户隔离或可靠任务取消；不建议直接用于不受信任用户或生产环境。

## 12. 更新与排错

源码已上传到 GitHub 后，服务器更新可执行：

```bash
cd /opt/remote-b-hub-source
git pull --ff-only
bash scripts/install-debian12.sh
```

已有的 `/etc/remote-b-hub/hub.env` 不会被安装脚本覆盖。更新前应确保没有正在执行的 CAD 任务，必要时备份 SQLite 数据库。

| 现象 | 优先检查 |
| --- | --- |
| `git clone` 下载的是空仓库 | GitHub 尚未上传程序文件 |
| `curl 127.0.0.1:18765/health` 失败 | `systemctl status`、`journalctl`、Python 依赖及监听地址 |
| 本地 health 正常、域名 B 不通 | FRP、HTTPS/TLS、反向代理端口与路径 |
| 返回 401 | A/B Token 对应关系及 `Authorization: Bearer ...` 是否被代理保留 |
| 电脑 B 显示离线 | 代理未启动、B 无法访问域名、DNS/TLS/防火墙问题 |
| SolidWorks COM 连接失败 | 是否同一 Windows 用户会话、SW 是否运行、`pywin32` 是否安装 |
| 创建零件失败 | `.prtdot` 路径、输出目录权限、重名保护、SolidWorks 弹窗/许可证 |
| Codex 识别不到工具 | 本地 MCP 注册路径、依赖、环境变量及 stdio 子进程日志 |

## 13. 下一阶段计划

在完成“Debian health → 域名 B health → 电脑 B ping → Codex MCP → SolidWorks COM”五级验证后，才考虑：

1. 为 SolidWorks 增加草图、尺寸、拉伸、切除、装配与保存/重建检查的**受限 API 工具**。
2. 增加 Python、MATLAB 等指定程序/脚本的安全执行模块（固定工作区与白名单）。
3. 按需增加桌面截图与 UI Automation，支持偶尔的图形操作；它并非 Codex 内置 Computer Use 自动穿透到电脑 B。
4. 增加任务取消、超时、审计日志、凭据轮换、数据库维护及执行队列隔离。

---

**仓库：** <https://github.com/zuiaishenzi/remote-b-hub>  
**协议与部署边界：** 本文描述的是项目设计及已编写的 MVP 功能，最终以实际代码版本及部署验收结果为准。

 
## 15. 通用 SolidWorks 建模方案（试验性）

新增 `computer_b_sw_recipe(recipe)`：用结构化 JSON 描述零件或装配体。**不是**任意 Python、VBA、PowerShell 或 COM 方法调用。NAS 与 Windows B 共享严格的 schema 校验规则，并限制文件名、零件数量、草图点数、特征步骤与尺寸。默认不覆盖现有文件；输出在 `D:\codex\output`。

### 零件示例：直径 30 mm、长 60 mm 的圆柱

```json
{
  "doc_type": "part",
  "name": "Cylinder_001",
  "operations": [
    {
      "op": "boss_extrude",
      "plane": "front",
      "profile": {"type":"circle", "cx_mm":0, "cy_mm":0, "radius_mm":15},
      "depth_mm": 60
    }
  ]
}
```

零件首版支持：`rectangle`、`circle`、`polygon` 草图和 `boss_extrude`、`cut_extrude`。`polygon` 允许最多 512 个顶点，可用在渐开线齿廓**离散近似**，但还不是精确的样条/齿根过渡曲线。所有拉伸基于模板前视/上视/右视基准面；切除相对全局基准面，方向可能要设置 `reverse`。暂不支持特征基准面、完整草图尺寸约束、圆周阵列、参数修改、圆角和倒角。

### 装配体示例：两个已有零件的前视基准面重合

```json
{
  "doc_type": "assembly", "name": "Assembly_001",
  "components": [
    {"id":"base","file":"Base_001.SLDPRT","position_mm":[0,0,0]},
    {"id":"link","file":"Link_001.SLDPRT","position_mm":[0,0,20]}
  ],
  "mates": [
    {"type":"coincident",
     "a":{"component":"base","plane":"front"},
     "b":{"component":"link","plane":"front"}}
  ]
}
```

装配体支持插入同一输出目录内已有的 `.SLDPRT`；支持显式引用基准面（front/top/right）或指定实体名与类别（PLANE/FACE/AXIS），并尝试创建 `coincident`、`concentric`、`parallel`、`perpendicular`、`distance`、`angle` 配合。距离值用毫米，角度值用度。**这部分 COM 选择/配合调用尚未经过 Windows B 的实机验证，属于试验接口**。不能据文件保存成功判断配合正确或完全约束；必须在 SolidWorks 检查配合特征树、欠定义状态、干涉及自由度。零件文件不能被覆盖，未实现原位修改装配体。

### 上线步骤

1. 确保 NAS、A、B 都拉取最新 GitHub 代码。NAS 需要将 `linux-server/server.py` **和** `linux-server/sw_schema.py` 同时复制到 `/opt/remote-b-hub/`，之后重启 `remote-b-hub` 服务。先用 Python `py_compile` 检查两个文件；**缺少 sw_schema.py 会导致服务启动失败**。
2. Windows B 不要覆盖已在本机修复的 `agent.py`，停止原来的 `box_agent.py`，改运行 `py -3 .\windows-b\sw_agent.py`。运行时依旧需要 `REMOTE_B_SERVER_URL`、`REMOTE_B_AGENT_TOKEN`。不要同时运行两个轮询代理。
3. Windows A 更新 `windows-a/mcp_bridge.py`，在已配置 A 端环境变量的 PowerShell 中重启 Codex，确认 `/mcp` 显示八个工具。
4. 建议先使用圆柱零件方案进行端到端测试，随后测试多次拉伸/切除，**最后再试装配体配合**。每一步均检查文件的实际几何、模型重建和装配配合状态。如果任务返回 error，保留完整 error 和 Job ID。失败后可能留下打开的未保存 SolidWorks 文档，需要手动清理。


## 16. 驱动尺寸与草图完全定义（实验性更新）

新增模块 `windows-b/sw_constraints.py`，默认启用严格约束检查。创建圆形草图时调用 `AddDiameterDimension2` 创建可编辑的直径驱动尺寸；矩形尝试用 `AddDimension2` 为边添加宽、高驱动尺寸。创建后优先检查活动草图的 `GetConstrainedStatus`：欠定义时尝试 `FullyDefineSketch`，如果仍不满足完全定义则任务失败，并且**不保存目标文件**。保存前检查 `ForceRebuild3(False)`。结果返回实际草图状态及驱动尺寸名称，不再硬编码 `sketch_dimension_constrained: false`。

**局限与验收要求：** 此代码尚未在 Windows B 的 SolidWorks 2023/pywin32 环境验证。草图约束、自动尺寸和 COM 参数可能需要适配。严格模式的多边形现在会直接拒绝：离散齿形不能伪装成完整驱动设计。若确实要测试旧式欠定义模型，可显式传递 `"allow_underdefined": true`，最终返回每张草图的真实状态，并在报告中清楚标注；**不建议用于工程设计交付**。装配体会尝试读取组件约束状态并返回，但机构运动自由度、配合正确性仍需人工/后续系统验证。

首先完成一个直径 30 mm、高度 60 mm 的新圆柱测试，**使用全新文件名** `Cylinder_Parametric_001`。请求格式与旧版 `computer_b_sw_recipe` 一样，新增的 `allow_underdefined` 默认是 false。成功后在 SolidWorks 逐项核对：直径是否为驱动尺寸、圆心是否受约束、草图是否完全定义、拉伸深度是否正确、特征树是否无错误。原有 `Cylinder_Test_001` 不受影响。

### 发布顺序

NAS：在 `/opt/remote-b-hub-source` 更新源码后，同步部署 `server.py` 和 `sw_schema.py` 至 `/opt/remote-b-hub` 并重启服务。Windows B：`git pull` 后检查 `sw_constraints.py`、`sw_recipe.py`、`sw_schema.py` 的 Python 语法；停止旧代理，重新运行 `py -3 .\\windows-b\\sw_agent.py`。Windows A：通常不需要更改 MCP 工具入口，但需重启 Codex 会话以加载文档中的新说明。

**目前尚未增加“直接改写已有 SLDPRT 的参数”功能**。需要在约束及尺寸命名的实机验证通过后，以生成新版本、不覆盖原始文件的方式实现。


## 17. 失败诊断与安全修订（实验性）

新版任务会保存完整结构化 recipe、最新 progress 及错误 diagnostics。Windows B 可用新入口 `windows-b/diagnostic_agent.py`，代替 `sw_agent.py`（**不要同时运行多个代理**）；失败时回传截断的 Traceback，方便 Codex 判断是 COM 获取实例、草图、尺寸、重建还是保存错误。错误信息可能包含 Windows 路径与零件名称，仅在可信私有服务使用；不要公开完整日志或 Token。

新增 MCP 工具 `computer_b_revise_recipe(job_id, recipe)`：读取失败任务与原始 recipe，修正并提交**完整新配方**，文件名必须与旧版不同。旧任务和旧 CAD 文件不被覆盖。最大建议自动尝试 3 次；遇到相同错误且配方未发生有效变化、SolidWorks 未启动、许可证/文件权限问题、拟关闭严格约束或改变机械设计意图时停止并要求用户处理。没有任意宏/Python/PowerShell 执行接口。

升级 NAS 必须同时复制 `linux-server/server.py` 与 `linux-server/sw_schema.py` 到 `/opt/remote-b-hub`；服务重启会把处于 running 的旧任务标记 interrupted。Windows B 更新后执行 `py -3 .\\windows-b\\diagnostic_agent.py`；Windows A 更新后重启 Codex，应有 9 个 pc-b MCP 工具。

**已知限制：** 新实现能让 Codex基于错误详情创建修订版本，但不是保证所有 COM 异常能够自动修好，更不等于能直接修改已保存零件内部特征。它依然缺少成熟的齿轮渐开线及圆周阵列、装配齿轮运动配合、可靠细粒度阶段日志、特征检查与模型几何验证。当前原脚本的 float-not-callable、COM 参数不匹配需要后续实机修复，不应靠允许欠定义来绕过。
