# A 上的 Codex 分步控制 B 的 SolidWorks 2023

新增两个 MCP 工具，工具总数由 16 增至 18：

- `computer_b_sw_session()`：读取真实活动文档、路径、修改标记和最多 120 个顶层特征。不重建、不保存，不要求开启脚本权限。
- `computer_b_sw_script(code, timeout_seconds=60)`：在 B 当前登录会话，通过 Python COM 分步读写 SW。返回任务 ID，必须用 `computer_b_job` 读取真实结果。

已有 C# 文档查询、鉴权截图及严格 recipe 继续可用。新增通道不要求另外下载 Interop DLL；Python COM 使用已安装 SW 的 COM 注册。C# 查询仍需要 B 自己的 SW2023 Interop。

## 部署

NAS、A 的 MCP 源码及 B 客户端都必须更新。只替换 EXE 不会更新 NAS 或已注册的 MCP Python 源码。

NAS 在仓库目录运行：

```bash
git pull --ff-only
sudo bash scripts/install-debian12.sh
curl --fail http://127.0.0.1:18765/health
```

`health.capabilities` 应包含 `sw_script`；安装脚本保留已有 Token。生产升级前按现有部署说明备份数据库和配置。

A 更新其 pc-b 注册所指向的仓库，重启 MCP 连接；`/mcp` 应能发现上述两个工具。A 桌面新增“SW 脚本”窗口，可直接编辑脚本、设置超时、提交任务，也可单独读取状态。

B 替换 `RemoteBHub.exe`。停止代理，勾选“允许 A 执行完整权限 SW Python 脚本（可修改文件；非沙箱）”，保存并启动代理。此选项默认关闭，原 Token、模板和输出目录保留。截图仍需单独勾选，不涉及实时视频配置。

完整权限脚本可以访问 B 用户的文件和系统，不是安全沙箱；只向可信任的 A 开放现有 Token 通道。子进程不会主动接收 relay Token 环境变量，但这不是凭证隔离保证。

## 使用

1. 检查 B 在线并读取 `computer_b_system_info`：确认实际执行器版本、`allow_sw_scripts`、`screenshots_enabled`、`cad_paused`。
2. 调用 `computer_b_sw_session` 并查询任务，核对当前活动文档。
3. 首次脚本验收只执行 `result = snapshot()`，不修改或保存文档。
4. 后续每次提交一个清晰的编辑步骤，查询实际结果。不可把脚本成功等同于模型验收成功。
5. 使用 C# 查询、尺寸与几何测量、约束与重建检查和截图验证；保存需在脚本中显式执行并返回真实路径、文件大小和 SW 返回值。

脚本可使用以下变量：

```python
# 默认只读示例；长度使用米，角度使用弧度
result = snapshot()
log("active document inspected")
# sw: ISldWorks COM 对象
# model: 活动 IModelDoc2，可能为 None
# read(obj, member): 兼容 COM 方法/属性读取
# output_dir, part_template, assembly_template: B 已配置的路径
```

`result` 必须是可 JSON 序列化字典，不可放 COM 对象或 NaN。脚本上限 24000 UTF-8 字节，超时 10–300 秒，结果和日志有大小上限及截断标记。

结果包含脚本 SHA256、执行前后文档快照、日志、耗时及本地审计 ID；失败任务在 `diagnostics.script` 保留日志、执行前快照和脚本 traceback。本地记录位于 B 配置目录 `script-runs/<id>/`。不要把密码写进脚本或输出。

## 超时与异常

异常不会自动重试，也不会回滚已经发生的 COM 修改。先读 traceback 和当前模型，再提交不同的修正脚本。

超时不强杀 SW 或脚本进程，因为正在执行的 COM 调用可能继续改变模型。B 写入 `cad-state-unknown.json`，后续 CAD 请求停止执行。B 操作员检查 SW、停止代理，等待脚本进程结束后，点击“核对 CAD 状态后解除脚本暂停”。读取状态后再继续，不得重复超时脚本。

## 验证边界

自动测试覆盖协议与鉴权、真实 Python 执行契约、结果/日志预算、完整 traceback、权限关闭、Token 环境变量移除和超时暂停；这些测试不模拟或声称真实 CAD 建模成功。

SW2023 实机验收必须记录 B 的实际任务 ID 和执行器版本。未完成该验收前，不宣称齿轮、装配配合、渐开线或运动学已验证。此升级提供 COM 脚本能力，不包含远端桌面鼠标键盘接口或实时视频。
