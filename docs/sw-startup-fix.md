# SolidWorks 自动启动失败：desktop-6-1 修复

2026-10-20 的真实 B 端任务 `808f0f0a-62c6-4f8d-9f68-ff551cf501c4` 失败于：

```text
desktop_worker.py:46
win32com.client.GetObject("winmgmts:")
pywintypes.com_error: -2147221020（无效的语法）
```

B 当时运行 desktop-6-1，源码提交 `01236c1217b206814269b6b54ac7d987104c02b3`。
该错误发生在检查已有 SW 进程时，尚未执行启动命令。此前手动打开 SW 后 COM 连接成功，
是因为已经打开的 SW 绕过了这段进程检查。desktop-6-1 沿用了这段旧逻辑。

## 修复

- 使用 Windows 原生 Toolhelp32 只读进程快照和 ProcessIdToSessionId，移除启动过程的 WMI 依赖。
- 只检查当前登录会话；发现 SW 正在启动时等待 COM，不重复创建另一个 SW。
- 进程检查失败时明确报错，不盲目启动。用户已请求停止时，不再发送启动命令。
- 日志区分 COM 未就绪、检查进程、发送启动请求及 PID、等待 COM、超时和就绪。
- 代理运行时的“启动 SW”按钮改为本地请求：代理完成当前任务后处理，使用已保存的 SW 路径。
  该请求不经 NAS、不增加远程代码执行接口；停止时取消待处理请求，过期请求会被丢弃。

原生 API 依据：
[CreateToolhelp32Snapshot](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot)、
[PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)、
[ProcessIdToSessionId](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-processidtosessionid)。

## 更新与检查

1. B 端点击“检查更新”安装最新稳定版；无需重装 SW，也不需要为此更新 NAS。
2. 核对日志中的 release_tag 已改变，仍为6-1说明旧代理尚未退出或更新未完成。
3. 检查“SOLIDWORKS 程序”路径是本机真实的 SLDWORKS.exe，路径修改需先保存。
4. 点击“启动 SW”，观察启动请求/PID/COM就绪日志；也可由 A 提交一次 solidworks_status 任务检查按需启动。
5. 若仍超时，保留完整日志，检查 B 当前交互会话、许可证弹窗及 SW 是否响应。

验证包含真实 Windows 进程枚举（无 COM 初始化的线程）、真实子进程的会话过滤，
以及启动/等待/取消/超时/本地请求的回归测试；打包版自检也执行原生进程快照。
这些不冒充 B 的真实 SW 冷启动结果，须在 B 更新后记录实际 COM 连接任务。
