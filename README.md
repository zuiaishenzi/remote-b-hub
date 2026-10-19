# Remote B Hub

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
| SolidWorks 参数化特征/装配建模 | **未实现** | 后续通过 SolidWorks API 扩展 |
| 远程 GUI 截图、鼠标键盘/Computer Use | **未实现** | 后续需专门的 GUI 执行模块 |
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

电脑 A 运行 Codex CLI，并通过本地 stdio MCP 桥接程序把工具调用转发至 Linux 服务器的 HTTP API。安装 Python 3.11+，将仓库中的 `windows-a/mcp_bridge.py` 和 `windows-a/requirements.txt` 放入 `C:\RemoteB\`。

在 PowerShell 中执行：

```powershell
cd C:\RemoteB
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

$env:REMOTE_B_API_URL = 'https://域名B'
$env:REMOTE_B_CLIENT_TOKEN = Read-Host '请输入 Debian 中的 HUB_A_TOKEN'

codex mcp add pc-b -- C:\RemoteB\.venv\Scripts\python.exe C:\RemoteB\mcp_bridge.py
codex mcp list
codex
```

**注意：**必须在设置环境变量的同一个 PowerShell 会话中启动 Codex，使它的 MCP 子进程能够读取上述变量。若从桌面快捷方式启动 Codex，可能无法继承终端中的环境变量，需要另外配置安全的持久化凭据注入方式。本项目当前针对 **Codex CLI**，尚未验证各桌面应用的 MCP 配置入口。

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