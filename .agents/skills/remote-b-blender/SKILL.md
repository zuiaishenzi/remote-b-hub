---
name: remote-b-blender
description: 通过 pc-b MCP 在电脑 B 的 Blender 中建模、编辑场景、材质、修改器、动画、渲染和保存；由 A 控制并核验真实任务、图像和文件。用于明确的远端 B Blender 请求，不用于 A 本机 Blender 或 SolidWorks。
---

使用 A → 现有 NAS → B 代理 → Blender 主线程桥接。无需公网 Blender 端口。

先检查 `computer_b_status` 和 `computer_b_system_info` 的真实任务结果：B 要在线且支持 `blender_control`。工具未发现时需重新连接 pc-b；旧 NAS 拒绝 operation 时需升级 NAS，不能把请求发送成功当执行成功。

`computer_b_blender_status` 不启动 Blender；`computer_b_start_blender` 显式启动或复用已有桥接实例。若 Blender 已运行但无桥接，B 设置页导出 ZIP，在 Blender 偏好设置安装并启用 Remote B Hub Blender Bridge，不重复开第二个实例。B 本地需开启“允许 A 执行 Blender 指令和完整权限 Python 脚本”；这是与 SW 分开的完整用户权限授权，不是沙箱。

先用 `computer_b_blender_scene` 读取文件、dirty、单位和场景物体；返回最多 80 个物体，`truncated` 为真时以有针对性的小脚本继续查询。保留用户当前未保存工作，独立验收使用新场景、新文件名。

用 `computer_b_blender_tools(name)` 查询 RFingAdam 固定版本指令的完整参数 schema，再调用 `computer_b_blender_command`。目录的 218 项表示接入范围，不代表所有版本、上下文、AI 后端均通过验证。基本建模不需要第三方 AI Key；外部生成、资源网站、MSFS 等能力可能需单独配置，使用前核对。

复杂操作使用 `computer_b_blender_script`，可用 `bpy`、`snapshot()`、`output_dir`、`log()`，设置 JSON 字典 `result`。脚本在 B Blender 主线程运行，坐标为 Blender 单位，旋转为弧度；根据 `scene.unit_settings.scale_length` 明确毫米换算。上游个别指令的角度约定不一致，需要精确角度时用 bpy 并查询实际值。分步执行、输出少量针对性结果，避免长时间阻塞 UI。

每次提交用 `computer_b_job` 取得真实结果，读 request/progress/result/diagnostics；核对 before/after/log_tail/traceback。失败可能已部分修改场景，不能声称回滚。保存时显式检查目标不存在，返回真实路径、大小；重要结果再打开检查对象、几何和修改器，不能以视图或“任务成功”代替验收。

超时或断线时保持 Blender 打开并暂停该控制通道；不原样重试。调用 `computer_b_blender_state` 读取暂停 ID 和迟到执行回执。只有旧命令有终态回执或原 Blender 进程及其子进程已经确认退出，且已经核对场景，才调用 `computer_b_resume_blender`，传当前 pause_id 和明确 acknowledgment。无终态且旧进程未确认退出时，不强杀进程、不删标记；需检查 B 并诊断。恢复不表示未保存的修改已保留。SW 和 Blender 的暂停、权限互相独立。

图像：先在 B 的 `output_dir` 内渲染 PNG/JPEG，再 `computer_b_blender_image` 上传简单文件名，需要 B 单独开启图像上传。之后列附件、下载并实际打开图像再评价，不假装看到截图；此功能不是实时视频，也不捕获整个桌面。UU 等视频需另行配置。

汇报实际任务 ID、文件路径/大小、完成与未验证项目。A 本地隔离 Blender 测试不能冒充 B 实机验收。
