# 桌面端更新与 AngelSix API 技能

## 如何使用更新按钮

A 的 RemoteBClient.exe、B 的 RemoteBHub.exe 都增加“检查更新”。
进入更新窗口后，点击“检查最新版本”；有稳定新版时再点“下载并更新”。
不再需要每次手动去 GitHub 下载、找旧文件并替换。

**已有 desktop-5-1 及更早 EXE 没有更新功能，首次需要手动下载这次新版一次。**
之后使用程序内按钮即可。A、B 分别更新各自程序；A 的更新按钮不会远程替换 B。
更新源为本项目 [GitHub Releases](https://github.com/zuiaishenzi/remote-b-hub/releases/latest)，
本次不要求 NAS 提供新的软件下载服务，也不修改用户的穿透配置。

请保留官方文件名 RemoteBClient.exe / RemoteBHub.exe，放在当前用户可写的固定文件夹。
程序目录在 C、D 等不同盘符均可；下载缓存位于当前用户的数据目录。
源码运行时可以检查版本，但不会替换 python.exe，请用 git pull 更新源码。

更新流程：

1. 只读取固定仓库的最新稳定 Release，检查更新清单的版本、源码提交、产品、大小和 SHA256。
2. 下载后核对大小、SHA256 和 EXE 文件头。新程序先在隔离目录执行自检；失败不退出原程序。
3. A 端退出后替换；B 端请求代理完成当前任务并回传，等待 GUI/代理退出，不强杀 SolidWorks。
4. 将新文件复制到原 EXE 同目录，以支持跨盘更新，保留旧版 `.previous-xxxx.exe`，再替换并重启。
5. 替换失败恢复原 EXE；目标被占用、权限不足或等待超时时保留旧版并记录错误。

只保留**已经保存**的配置，更新前请保存正在编辑的设置。
Token 仍是当前 Windows 用户的 DPAPI 密文；模板、输出路径、截图偏好及 A 工作目录继续使用原数据目录。
更新不会升级 Python MCP 源码仓库、NAS 服务或 SolidWorks 本身，也不会重写 CAD 文件。
MCP 桥接源码另用 git pull 更新并重新加载；A EXE 的技能包由 EXE 更新。
B 更新前代理运行时，更新后请求恢复代理；原本未运行时遵循保存的自动启动设置。

若更新失败，查看：

- A：`%LOCALAPPDATA%\RemoteBHubA\update-result.json`
- B：`%LOCALAPPDATA%\RemoteBHub\update-result.json`
- 自定义 --data-dir：对应目录下的同名文件。

原 EXE 旁保留带 `.previous-` 的备份供人工恢复。更新使用 GitHub HTTPS 和文件哈希校验，
不是额外的代码签名机制。下载缓存和旧版备份会保留，确认新版正常后可自行清理。

## AngelSix / SolidDNA 如何集成

用户指定的 [angelsix/solidworks-api](https://github.com/angelsix/solidworks-api)
固定审阅提交 `58787e2cefdcc03aebc15a51bd52ba151f3969d4`。
其中 SolidDNA 是 C# API 封装和教程，不是现成的远程建模 skill。
审阅版本默认引用 2020 Interop，目标框架 net472，不能据此认定 SW2023 已验证。
许可有 References 目录的额外使用条款，本项目没有复制其 SolidWorks DLL 或执行 ScriptRunner。

实际接入内容：

- 第三项项目技能 `solidworks-2023-interop`，包含版本固定的来源、许可、尺寸身份、单位及文档检查方法。
- 技能进入 A EXE 内置目录，也可由“安装到工作目录”安装；MCP 的 modeling_skills 指定该技能时返回参考知识。
- 固定 C# 控制器支持按名称读取最多20个尺寸，而非开放任意代码。
- NAS/B 共享校验 `dimension_names`，只允许 inspect 使用；读取不存在的尺寸返回明确错误项。
- 控制器与 Python 之间明确使用 UTF-8，支持“草图1”等中文名称。

调用示例，实际文件名和特征名应来自真实任务：

```json
{
  "action": "inspect",
  "file": "YourActualPart.SLDPRT",
  "dimension_names": ["D1@草图1", "D1@凸台-拉伸1"]
}
```

通过 `computer_b_sw_document` 提交，使用 job_id 读取真实结果。
目标文档须已打开；新 inspect 不会自动关闭或保存用户文件。
输出 `requested_dimensions` 包含 requested_name、full_name、system_value、read_only；
未找到/读取失败时为 error 项，不可据任务 done 判断所有尺寸已通过。
尺寸系统值按长度米、角度弧度解释，不能一律乘1000。仅查询当前活动配置。
此读取路径没有设置尺寸、运行脚本或新增旋转/圆角/阵列能力。

## 部署与验证边界

程序内更新：A/B 更新 EXE 即可，与 NAS 下载服务无关。
新增尺寸参数：必须同时升级 NAS 的 server.py/control_schema.py 和 B EXE，以及 A MCP 源码，
部署过程按 [脚本控制升级文档](script-control-upgrade.md) 执行，保留现有 Token 配置。
若 NAS 返回400，请读错误并先升级，不能将工具拒绝当作已检查 SolidWorks。

验证分层记录：

- 本地测试：版本比较、清单匹配、下载篡改拒绝、隔离自检失败、替换失败回滚、超时不替换、代理正常停止。
- 真实冻结 EXE：临时安装目录内运行旧程序、等待退出、备份、替换、重启新版、原 DPAPI 配置字节不变。
- C#：编译与受控 .NET 对象的只读尺寸测试，覆盖缺失尺寸及 NaN；不是 SolidWorks COM 实机验收。
- MCP：真实 SDK stdio 发现工具/新参数、读取第三项技能及参考、生成配方、拒绝非法尺寸参数。

新增 C# 尺寸接口尚需升级 NAS/B 后进行 SW2023 实机验收；
之前已成功的零件记录见 [建模技能验收](solidworks-skills.md)，不冒充本次接口测试。
双孔板模板仍被欠定义失败阻断，未擅自解除；精确齿轮/运动学仍未实现。
