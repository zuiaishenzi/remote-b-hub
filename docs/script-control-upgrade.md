# 脚本控制、诊断图片与 A/B 桌面端升级

主要编辑仍通过脚本和 SOLIDWORKS API 完成：原有 Python COM recipe 创建草图、
凸台、切除、插入零件和基本配合；新增固定 PowerShell 构建脚本与 C# Interop 控制器，
读取装配树/特征树、几何摘要，打开、重建、另存副本和关闭文档。
本次没有把全部建模执行器重写成 C#，也没有开放远程任意脚本、宏或 COM 表达式。
用户提供的 README 作为方案参考；其中规划中的实时视频、鼠标键盘控制不等于已实现。

## 本次能力与验收范围

| 功能 | 实现与边界 |
| --- | --- |
| B `RemoteBHub.exe` | 设置、DPAPI Token、自动启动 SW、代理及日志；本次修复关闭行为 |
| A `RemoteBClient.exe` | 加密保存 A Token、启动已安装的 Codex CLI、查询任务和实际图片预览 |
| 原有 recipe | 严格草图检查、拉伸/切除、插入零件和基本配合继续使用 Python COM |
| C# Interop | `inspect/open/rebuild/save_copy/close`；本地编译契约通过，需 B 实机验收 |
| 装配/几何检查 | 返回组件父级、抑制状态、特征、草图约束状态、实体面/边数及近似包围盒、质量属性；有截断标记及警告，不能代替完整工程验收 |
| 图片 | B 明确开启后采集 SW 窗口；独立鉴权上传、列出、下载；本地 NAS 测试通过，真实 SW 图形驱动下采集仍需实测 |
| 实时视频/远程鼠标键盘 | 本次未接入；需另行手动配置，见下文 |
| 精确渐开线、齿轮配合、运动学 | 本次未新增，不得把几何示意当成精确啮合传动 |

## 1. 先升级 NAS（需要手动操作）

新增接口要求 NAS、A 桥接和 B EXE 一起升级。仅替换 EXE 不会升级 NAS。
部署时先让 B 完成任务并停止代理，确认没有运行中的 CAD 任务，再在 NAS 执行：

```bash
cd /你的路径/remote-b-hub
git pull --ff-only
sudo systemctl stop remote-b-hub
backup="/root/remote-b-hub-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
sudo tar -czf "$backup" /opt/remote-b-hub /etc/remote-b-hub /etc/systemd/system/remote-b-hub.service
sudo chmod 600 "$backup"
sudo bash scripts/install-debian12.sh
curl --fail http://127.0.0.1:18765/health
```

备份包含 Token 和历史任务，只留在 NAS，不能上传 GitHub或发送给他人。
安装脚本保留既有 `/etc/remote-b-hub/hub.env` 中的 A/B Token；新版安装会同时复制
`server.py`、`sw_schema.py`、`control_schema.py`、`artifact_store.py` 并安装 Pillow。
`/health` 应返回 `protocol_version: 2` 和 `sw_document/screenshot/artifacts`。
随后通过既有 HTTPS 入口检查同一路径。反向代理需保留 Authorization 和 Content-Type，
允许至少 5 MiB 的图片请求体（例如将上限设为 6 MiB）；FRP/HTTPS 不自动修改。

升级失败先看 `sudo journalctl -u remote-b-hub -n 100 --no-pager`。
需要回退时停止服务，将上面备份解压恢复到原绝对位置，执行
`sudo systemctl daemon-reload` 和 `sudo systemctl start remote-b-hub`。
恢复数据库会回退升级后的任务记录，因此回退前也应保留当前目录的备份。

截图默认保存在数据库同目录的 `artifacts/`，可用 `HUB_ARTIFACT_DIR` 改位置；
自定义位置还需允许 systemd 的 `ReadWritePaths` 写入。
每张最多 5 MiB、每任务最多 3 张、总量最多 256 MiB、保留 48 小时，启动及每小时清理。
只接受真实 PNG/JPEG，不把图片字节塞进任务 JSON，也不提供免鉴权静态链接。

## 2. 更新 A

停止当前 Codex CLI 和旧 MCP 进程，仓库执行 `git pull --ff-only`；
有本地改动时先查看并备份，不能直接强制覆盖。重新启动 Codex 才会载入新版桥接。

从 [Releases](https://github.com/zuiaishenzi/remote-b-hub/releases/latest) 下载 `RemoteBClient.exe`。
填写 NAS HTTPS 地址、NAS 的 `HUB_A_TOKEN`、A 的真实仓库目录并保存。
配置保存在 `%LOCALAPPDATA%\RemoteBHubA\config.json`，Token 按当前 Windows 用户加密。
点“启动 Codex”会打开继承 `REMOTE_B_API_URL` / `REMOTE_B_CLIENT_TOKEN` 的 PowerShell。
仍需事先安装 Codex CLI，并按主 README 注册 `pc-b`；A EXE 不代为安装 CLI 或修改 MCP 注册。
它也不会向已有 Codex 桌面进程注入环境变量。

新版增加四个工具：

- `computer_b_sw_document(action, file?, new_file?)`：提交受限 C# 文档操作，随后查询 `computer_b_job`。
- `computer_b_screenshot()`：提交截图任务，不自动启动 SW。
- `computer_b_artifacts(job_id)`：列出任务的实际附件。
- `computer_b_get_artifact(artifact_id)`：鉴权下载到 A，返回绝对本地路径、大小和 SHA256。

模型必须再通过支持读取本地图片的工具打开返回的 `downloaded` 路径；仅看到 JSON 不等于看见画面。
也可在 A EXE 输入任务 ID → 列出截图附件 → 下载并查看，直接显示实际图片。

## 3. 更新 B 与关闭问题

旧版右上角“×”会最小化；旧版“退出启动器”在代理运行时先请求停止，需要等任务完成后
再点一次退出。替换前可按这个顺序退出旧版本，不要在 CAD 调用中强杀进程。

下载新版 `RemoteBHub.exe`，停止并退出旧版后替换，保留 `%LOCALAPPDATA%\RemoteBHub`。
新版“×”和“退出启动器”一次点击就关闭窗口、退出启动器并请求代理停止。
代理正在执行的调用会继续完成并尝试回传；网络失败时结果留在 `pending-result.json`，下次启动优先回传。
不会终止 SOLIDWORKS。若需持续接收任务，请点独立的“最小化驻留”。
启动器全部退出且代理停止后，A 的请求只会在 NAS 排队；需 B 登录自启或手动重新启动 EXE。

代理使用独立的 PyInstaller 解包目录，允许窗口关闭后完成当前任务；重新打开时会检测
尚未退出的代理，保留停止请求，避免重复启动。若 CAD COM 本身阻塞，后台代理退出时间取决于该调用，
窗口仍可关闭；这时检查日志并在 B 人工处理 SW 弹窗。

## 4. C# 本地依赖与实机检查（可能需要手动指定路径）

默认从配置的 `SLDWORKS.exe` 同目录下 `api\redist` 找
`SolidWorks.Interop.sldworks.dll`。例如安装在 `D:\SW\SOLIDWORKS Corp\SOLIDWORKS`，
对应 `D:\SW\SOLIDWORKS Corp\SOLIDWORKS\api\redist`。
若自动定位失败，在 B 的“Interop 目录”选择实际目录。
DLL 来自本机 SOLIDWORKS 安装，不从网络下载，也不随本项目分发。
参考 [SOLIDWORKS 2023 API 官方说明](https://help.solidworks.com/2023/english/api/sldworksapiprogguide/Welcome.htm)。

首次操作通过固定 `BuildInterop.ps1` 使用 Windows 自带 .NET Framework x64 C# 编译器构建，
缓存到 B 配置目录的 `interop-build/`，源文件或 Interop DLL 变化会生成新缓存。
缺少 DLL/编译器会回传真正错误，不自动安装或反复执行 CAD 操作。

先对一个可丢弃的新文件验收，所有任务都通过 `computer_b_job` 检查真实结果：

1. `computer_b_sw_document(action="inspect")`：读取当前打开文档；检查返回的特征/组件、警告和截断标记。
2. `open` 指定输出目录里的简单文件名，如 `Probe_001.SLDPRT`，以只读方式打开。
3. `rebuild` 对该已打开文件重建，不保存源文件。
4. `save_copy` 指定新的同类型 `new_file`，确认真实路径和非零大小；不覆盖已有文件。
5. `close` 仅关闭没有未保存修改的指定文件；若重建使其变为修改状态，应拒绝关闭，由 B 人工处理。

除当前文档只读检查外，文档引用只接受输出根目录内的 `.SLDPRT/.SLDASM` 简单文件名，
拒绝目录跳转和符号链接/目录联接。装配副本仍引用原组件，不能当成打包归档。
120 秒超时只报告状态未知，不自动重复操作。
本次 C# 编译测试使用编译契约 stub，不代表通过真实 Interop DLL 或 SW 2023 实机测试。

## 5. 图片与视频的手动配置

**图片：** NAS 升级完成后，在 B 停止代理，勾选“允许上传 SOLIDWORKS 窗口截图”并保存，
再启动代理。可选择“CAD 失败时自动截图”。截图仅使用 SW 窗口的 PrintWindow，
不会在失败后退回整屏截取；窗口最小化、图形驱动不支持或得到空白图时会明确报错。
必须在 B 真实运行一次截图并在 A 打开图片，确认没有黑屏。
CAD 原始 traceback 会保留，截图失败记录在 `diagnostics.screenshot_error`。

**视频：** 本次未实现实时视频，也未配置 RustDesk/WebRTC/FRP 视频通道。
如需连续观看，可另行在 A/B 安装并配置双方信任的远程桌面软件与访问认证；
需要中继/穿透时另外配置其服务。现有 NAS HTTP 端口不自动成为远程桌面或视频通道。
截图方案不要求额外视频服务或新端口。
未来接入自动鼠标键盘时还需要单独实现动作白名单、确认机制和实际客户端图像接口；
不能把 Codex CLI、Codex 桌面端或 ChatGPT Work 的能力直接视作可跨设备互通。

## 本地验证

`scripts/build-desktop.ps1` 运行回归测试、NAS API/实际 HTTP 队列测试、B EXE 的 DPAPI、
隐藏窗口启动与退出、冻结代理 HTTP 测试，以及 A EXE 的隐藏窗口/DPAPI 测试。
这些测试不连接生产 NAS，不建真实 CAD，也不能代替上述 B 端验收。
