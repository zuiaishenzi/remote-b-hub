# Windows B 桌面启动器

`RemoteBHub.exe` 将设置、代理启停、SOLIDWORKS 检查/启动及日志集中在一个窗口。
运行电脑无需单独安装 Python 或 pywin32。SOLIDWORKS 本身及许可证仍需在 B 上安装。

## 首次使用

1. 停止旧的 `diagnostic_agent.py` / `sw_agent.py` / `box_agent.py` 命令行代理。
2. 将 EXE 放到固定位置，例如 `C:\RemoteB\RemoteBHub.exe`，双击启动。
3. 填写 NAS 地址、**B Token（NAS 的 HUB_B_TOKEN）**、输出目录、零件/装配模板及
   `SLDWORKS.exe` 的实际位置。首次运行会预填当前环境中已有的 REMOTE_B 配置。
4. 在设置页保存配置，再到首页点击“刷新状态”和“启动任务代理”。运行时同一按钮切换为“停止任务代理”，停止过程不强杀当前任务。
5. 如需无人值守，勾选“Windows 登录后驻留”“代理意外退出后自动重启”及
   “CAD 任务到达时自动启动 SW”，再次保存。启用登录自启后不要移动 EXE。

“检查状态”会显示当前会话的 SOLIDWORKS COM 连接、NAS `/health` 和路径是否存在。
NAS 健康检查成功不等于 Token 正确；代理进入 `idle` 才表示已成功使用 B Token 轮询。
“启动 SOLIDWORKS”可本地启动；如果代理已运行，则由 CAD 任务路径管理 SW 的启动。

关闭窗口会立即退出窗口并请求代理停止；需要最小化时使用窗口标题栏按钮。
正在运行的任务会继续完成并尝试回传；网络失败的结果保留到下次启动。不会强杀建模或关闭 SW。
重新打开会检查是否还有代理在完成退出，避免重复启动。
更新 EXE 前也应先停止并退出旧版本。

## A 端能否自动启动 SW 和代理

可以在 **B 已开机、用户已登录、启动器驻留且相关选项开启** 时实现：

- 启动器打开/登录后自动启动任务代理；代理意外退出后自动重启。
- A 按原来的 MCP 工具提交 `solidworks_status`、创建零件或 recipe 任务。
- 代理收到 CAD 任务后先连接 SW；未启动时启动配置中的 EXE，默认最多等待 180 秒。
- COM 就绪后执行原任务；启动失败则回传真实错误，不假报模型成功。
- `ping` / `system_info` 不启动 SOLIDWORKS。
- 登录/许可证/启动窗口阻塞会导致超时，需要在 B 上处理；不会自动点击这些窗口。

这是一套当前用户会话中的驻留启动器，**不是 Windows Session 0 服务**。
SOLIDWORKS GUI/COM 需要交互式用户会话。如果 B 的启动器和代理全部退出，A 的
HTTP 请求没有接收者，只能在 NAS 排队。B 关机或用户未登录时也不保证能启动 SW。

界面的“服务”对应本机任务代理；NAS systemd 服务只能检查 `/health`，本程序不远程
SSH 启停 NAS。基础建模不增加任意远程命令执行接口；新增 C# 控制及截图需同步升级 A/NAS，
见 [脚本控制与诊断图片升级](script-control-upgrade.md)。

## 配置和日志

配置保存在 `%LOCALAPPDATA%\RemoteBHub\config.json`。Token 使用 Windows DPAPI
按当前用户加密，不写入 EXE、不提交 GitHub、不在界面日志中明文显示。
复制配置到另一个用户/电脑时需要重新输入 Token。

- `agent.log`：任务、SW 启动、建模阶段、结果及完整异常；轮转保留。
- `launcher.log`：界面检查及代理启停日志。
- `startup-error.log`：EXE/worker 启动失败时的错误，若存在应一并查看。
- `status.json`：最近的本机代理阶段和更新时间。
- `pending-result.json`：网络异常时尚未回传的任务结果；恢复后先回传，再领取新任务。

代理将阶段通过已有 `/progress` API 回传。A 的 `computer_b_job(job_id)` 可看到
`starting_solidworks`、`solidworks_ready`、`executing`、`modeling` 和 `completed`。
结果包含 `agent_log_tail`，失败诊断包含 traceback 和 `log_tail`，Token 会被遮盖。
新版还在 `value.executor` / `diagnostics.executor` 回传执行源码指纹和构建提交；
启动器标题与启动日志也会显示该版本，方便核对实际部署。
任务已失败/完成但响应丢失时，旧 NAS 可能返回 409；此时需检查 NAS 任务记录和本地
pending-result 文件，不应因结果冲突再次执行同一个 CAD 操作。

NAS 现有在线指示依赖领取任务/回传结果时间；长时间 SW 启动或 COM 调用期间，
可能显示心跳过期。应同时查看任务 progress 与本地日志，不能仅据 online 判断建模已停止。

## 获取与构建

源码通过 GitHub 更新：`git pull --ff-only`。EXE 内嵌执行代码，更新源码不会热更新
已运行的 EXE；应下载新的 EXE，停止并退出旧版本后替换。设置与日志位于用户目录，保留不丢失。

仓库的 Windows Desktop 工作流会在相关源码更新时测试、打包并发布 GitHub Release。
从仓库 Releases 下载 `RemoteBHub.exe`。本地也可以双击根目录 `build-desktop.bat`，
构建产物为 `dist\RemoteBHub.exe` 和 A 端的 `dist\RemoteBClient.exe`；构建端需要 Python 3.14 和 Git。

构建执行全部回归测试、冻结 EXE 模块/DPAPI 自检及隐藏窗口的 GUI 启动测试。
这些检查不能代替 B 实机的 SW、NAS Token、开机登录和任务验收。

验收建议：先运行 EXE 检查状态，再由 A 发送 ping；然后在 SW 未启动时提交
`computer_b_solidworks_status`，确认它能启动 SW 并返回真实版本。最后用全新文件名
测试严格矩形和圆柱，检查尺寸、完全定义、重建、保存及 A 端日志。不要同时运行旧代理。
