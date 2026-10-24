# A 控制 B 的 Blender

Blender 与 SolidWorks 共用现有 **A → NAS → B** 鉴权任务通道，独立维护权限和暂停状态。无需新隧道或公网 Blender 端口。A 无需安装 Blender，B 需要安装 Blender；优先使用 4.2 LTS。此版本在官方 Windows Blender **4.2.23 LTS** 便携版进行隔离测试，不能把 A 上的测试当作你的 B 已通过验收。

## 集成来源与范围

选用用户提供的 [RFingAdam/mcp-blender](https://github.com/RFingAdam/mcp-blender)，固定提交 `efbafb6a9e019a03a5887ff943462715e0f386dc`，内置其 Blender 插件指令处理器与 218 条工具参数目录，不在 B 临时拉取最新版或依赖 PyPI 同名包。

比较了 [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender)，它同样需要 Blender 内插件。此处选择 RFingAdam 的细粒度指令，便于对象、网格、材质、修改器、动画等操作按 schema 调用；复杂操作直接用 bpy Python。更换为现有 NAS 队列和本机鉴权桥接，原始上游无鉴权 socket 服务不启动。

**218 项是接入的指令目录，不是 218 项全部实机通过。** AI 生成、资源下载、MSFS、烘焙和特定交互上下文可能需要额外服务、依赖、账号、网络或版本适配。基础建模无需外部 AI Key。

上游 README 的 MIT 文字与 LICENSE 冲突，本项目按其实际 **AGPL-3.0-or-later** LICENSE 保留许可及完整源码；详见 [来源与分发说明](../third_party/rfingadam/NOTICE.md)。

## 更新顺序

本次增加新的 NAS operation，需要更新 NAS、A 桥接和 B EXE；现有 Token 沿用。

NAS 的 `/opt/remote-b-hub` 是部署目录，不要求是 Git 仓库。以 root 分别执行以下命令，赋值后必须换行或 `&&`，不能把赋值和 `git clone` 无分隔地粘在一起：

```bash
update_dir=$(mktemp -d /root/remote-b-hub-update.XXXXXX)
git clone --depth 1 https://github.com/zuiaishenzi/remote-b-hub.git "$update_dir" && bash "$update_dir/scripts/install-debian12.sh"
curl --fail http://127.0.0.1:18765/health
```

健康接口 capabilities 需要包含 `blender_control`。更新部署不会安装 Blender 或打开新端口。

A 的实际 Git 仓库执行 `git pull --ff-only`，保存原连接配置，然后重新连接 pc-b MCP（必要时退出并重新打开承载 MCP 的 Codex / ChatGPT 桌面进程）。新的工具数量为 **30**，其中 Blender 新增 9 个；原 21 个 SW/通信工具保留。A 客户端更新不是代替源码 MCP 桥接更新。

将新版 `RemoteBHub.exe` 放到 B，退出旧启动器后替换并启动。**拉源码不会热更新正在运行的旧 EXE。**

## B 设置

停止代理，等待当前任务完成，在设置页的 Blender 分组中配置：

- **Blender 程序**：指向 `blender.exe`；留空自动从 Blender Foundation 常用安装目录或 PATH 查找，便携版需手动指定。
- **Blender 输出目录**：默认 `D:\codex\blender-output`，与 SW 输出目录独立。
- **本机桥接端口**：默认 `18766`，仅监听 `127.0.0.1`，无需 NAS、防火墙或隧道开放。
- **自动启动**：Blender 任务到达且尚无进程时启动；已运行但无桥接时提示安装插件，不重复开实例。
- **允许 A 执行 Blender 指令和完整权限 Python 脚本**：默认关闭，与 SW 权限分开；脚本与 Blender 当前用户同权限，**不是沙箱**。
- **允许上传 Blender 输出图像**：默认关闭，需图像反馈时启用。

保存后启动任务代理。设置页“启动 / 检查 Blender”将请求交给现有代理，排在当前任务之后；代理未运行时本地直接启动。

若 Blender 由 B 启动器启动，会通过 `--python` 自动加载桥接。若 Blender 已手动打开，点击“导出 Blender 桥接插件”，在 Blender **Edit → Preferences → Add-ons → Install from Disk** 安装 ZIP 并启用 **Remote B Hub Blender Bridge**。一次安装后插件会随 Blender 启用。配置中的本机桥接 secret 自动生成，与 NAS A/B Token 分开，ZIP 不包含 secret。更改桥接端口/输出目录后，需停止并重新启用插件，或在保存工作后重新打开 Blender。

## A 的控制入口

A 首页点击 **Blender 控制**：检查连接、启动、读取场景、暂停状态、Python 编辑器、开源指令与完整参数说明、获取输出图像。所有执行使用同一个鉴权任务接口，任务 ID 和结果在主窗口日志页读取。

MCP 工具：

| 工具 | 用途 |
|---|---|
| `computer_b_blender_tools(name?)` | 本地目录；指定名称取得完整参数 schema，不连接 B |
| `computer_b_blender_status` | 检查桥接，不自动启动 |
| `computer_b_start_blender` | 显式启动 / 复用已有桥接实例 |
| `computer_b_blender_scene` | 实际场景、文件、dirty、单位、对象/修改器，最多 80 个对象 |
| `computer_b_blender_command` | 调用固定上游指令，例如 `object_create`，需 B 授权 |
| `computer_b_blender_script` | Blender 主线程 bpy 脚本，返回 JSON 字典 `result` |
| `computer_b_blender_state` | 不接触 bpy，查询暂停 ID、审计与迟到回执 |
| `computer_b_resume_blender` | 精确匹配暂停且旧命令有终态回执时，确认状态后恢复 |
| `computer_b_blender_image` | 从 B Blender 输出目录上传指定 PNG/JPEG，需 B 图像授权 |

所有远端工具返回排队 ID，需通过 `computer_b_job` 读取真实执行结果。目录工具只说明指令存在，不证明运行成功。

脚本可用 `bpy`、`snapshot()`、`output_dir`、`log()`，设置 JSON 字典 `result`。脚本不自动保存、不自动回滚；失败可能已有部分修改。单位遵循实际 `scene.unit_settings`，旋转使用弧度，不直接将 SW 的毫米当 Blender 坐标。返回 snapshot 包含 before/after；大场景按需小范围查询。普通 Python 第三方包若 Blender 自带解释器未安装，需要另行配置，不复用 A 的 Python 环境。

需要保存时显式选择新文件名并检查不存在，再返回路径/实际字节数；重要成果重新打开核对。原始上游 `save`/`save_as` 有保存和覆盖能力，应由 A 根据用户任务决定，不能承诺全权限脚本受到路径沙箱限制。

## 超时、暂停与日志

命令超时 10–300 秒。执行前记录审计并预留 Blender 暂停锁，收到终态回执才清除。超时、断线或 B 代理异常退出时，保留 Blender 进程和锁，不杀进程、不原样重试。

状态工具读取 `blender-runs/<request-id>` 中的迟到回执。旧命令已有终态且 A 核对了模型/错误后，才能使用当前 `pause_id` 与 `acknowledge_state=true` 恢复。尚无终态时拒绝恢复，即便只是渲染慢；需检查 B。此恢复不证明几何正确。SW 暂停标记不受影响。

B 配置目录下有 `agent.log`、`blender-start.log`、`blender-runs` 的 request/state/response 与恢复审计。错误返回 traceback、部分日志及执行器版本；相同 request ID 回执可读取但不重复执行。日志与结果有大小上限，返回超限也会报告“可能已修改场景”，不能按未执行重试。

## 图像与视频

图像需手动开启 B 的 Blender 图像上传开关。先在 Blender 输出目录渲染 PNG/JPEG，再通过简单文件名上传。返回附件后在 A 下载并打开查看；不捕获整个桌面。文件 ≤10MiB，转换为受保护的 JPEG 附件，沿用现有过期和鉴权机制。

**实时视频 / 键鼠远控仍使用单独配置的 UU、ToDesk 等服务。** 本次没有新增视频传输、隧道或这些服务的账号设置。

## 已完成的检查与边界

`tests/blender_integration.py` 在隔离工厂场景中运行真实官方 Blender：鉴权 NAS 入队 → B 执行 → 实际场景读取 → 上游创建物体/材质/修改器 → bpy 保存新 `.blend` → 渲染 → 鉴权附件取回 → 重新打开检查对象 → 人为错误 traceback → 人为只读延时超时 → 迟到终态 → 精确暂停恢复。支持用打包 EXE 作为实际 worker 再执行同一流程，CI 在发布前运行此模式。

这验证了本地真实 Blender 与协议/EXE，不等于 B 的 Blender 已部署、某个复杂模型质量达标或全部 218 个上游指令可用。B 实机验收需另外检查真实版本、任务 ID、实际文件路径/大小与画面。
