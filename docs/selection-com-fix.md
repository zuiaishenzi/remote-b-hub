# SOLIDWORKS 2023 草图选择 COM 修复

基于 `185cb82`。2026-10-19 用户在 Windows B 实机确认：
`SelectionManager.CreateSelectData` 返回 `CDispatch` 且 mark=0；四条矩形边和一个圆
均通过 `Select2` 选中。**选择阶段已实机通过；尺寸、全定义及拉伸保存仍待验证。**

## 问题定位

任务链路是 A 的 MCP → NAS 的 FastAPI/SQLite 队列 → B 的
`diagnostic_agent.py` → `sw_recipe.py` → `sw_constraints.py`。
本次独立脚本直接访问本地 COM，因此报错发生在 B 的选择执行代码。

1. 当前 B 读取 `ISelectionManager` 报“无法读只写属性”。修复后不再读取此属性。
2. 原脚本用 `callable(member)` 判断 `CreateSelectData` 是方法还是返回值。
   但 pywin32 `CDispatch` 自带 `__call__`，返回的 `ISelectData` 也可能满足
   `callable()`。再次调用它会访问默认成员（DISPID_VALUE），而不是调用工厂。
   因此原来的“找不到成员”**不足以证明 CreateSelectData 本身不存在**。
   这与现场输出吻合，仍需修复后的脚本确认现场实际行为。
3. `com_read` 现在直接保留带 `_oleobj_` 的 COM 接口；普通 Python 方法仍调用一次。
   这也修复了草图执行器里同类的属性读取问题。
4. `select_segment` 优先调用 `ISketchSegment.Select2(False, 0)`，避免传递
   `ISelectData`。官方将 Select2 标为 obsolete，故保留修正后的
   `SelectionManager.CreateSelectData` + `Select4` 回退路径。
   每次尝试前清空选择；两条路径均失败时保留两条错误并终止尺寸创建。

严格约束检查、尺寸检查、保存条件未放宽。选择测试通过不等于全定义建模通过。

## 更新 Windows B

本次需要替换的执行文件只有：

- `windows-b/solidworks_box.py`
- `windows-b/sw_constraints.py`
- `windows-b/probe_selection_manager.py`

补丁包还含测试和本文档，不含 `agent.py`、配置、令牌或 CAD 文件。
如果 B 的以上三个文件也有本地修改，应先审查并合并差异。

统一通过 GitHub 分发代码。上传端双击仓库根目录的 `upload-github.bat`，
会检查语法、运行回归测试、提交全部未被忽略的修改并推送当前分支。
GitHub 登录或推送失败时，脚本停止并保留错误，不强制推送。

在 B 暂停轮询代理后，先检查本地差异，再拉取：

```powershell
cd C:\RemoteB\remote-b-hub
git status --short
git pull --ff-only
py -3 -m py_compile .\windows-b\solidworks_box.py .\windows-b\sw_constraints.py .\windows-b\probe_selection_manager.py
py -3 -m unittest discover -s tests -p test_sw_constraints.py -v
```

若有本地手工修改，先备份并审查；不要使用 `reset --hard` 丢弃修改。
如果 pull 失败，先解决差异再继续，不要把失败当作已更新。
本次修复只涉及 B，不需要重启 NAS 或修改 A 的配置。其他设备也可以
在各自仓库执行 `git pull --ff-only` 同步源码；NAS 的源码更新与正式部署仍是两步。

## 分阶段实机验证

先用同一交互式用户启动 SOLIDWORKS 并激活一个文档，执行默认只读探测：

```powershell
py -3 .\windows-b\probe_selection_manager.py
```

期望输出 `SUCCESS: data type: ... mark: 0`。若仍失败，保留完整输出；
`Select2` 不依赖管理器，可以继续单独验证。

下面的命令会**创建一个新零件并添加测试草图**，不修改既有文档，不保存文件，
不创建尺寸，不判断全约束；新零件会留在 SOLIDWORKS 中供检查：

```powershell
py -3 .\windows-b\probe_selection_manager.py --select-test
# 若模板路径不同：
py -3 .\windows-b\probe_selection_manager.py --select-test --template 'C:\实际模板路径\Part.prtdot'
```

验收：四条矩形边和一个圆分别输出 `SUCCESS`，末尾出现
`SELECTION TEST PASSED`；失败时退出码为 1。成功路径会注明 Select2 或 Select4。

选择验证通过后，重启原 `diagnostic_agent.py` 进程以加载新模块，
沿用原 PowerShell 的环境变量。再用**全新文件名**测试严格矩形/圆柱配方。
必须另外检查驱动尺寸、`all_sketches_fully_defined`、重建及实际文件信息。
如果在后续尺寸/全定义阶段出错，需保留 traceback；不能当作选择修复未生效，
也不能当作建模已验收。

## 下一步：严格参数化零件测试

现在可以用 `windows-b/probe_parametric_part.py` 直接调用生产的
`sw_recipe.execute_recipe`，无需通过 NAS 排队。先暂停 B 的轮询代理，避免其他任务
同时操作 SOLIDWORKS；保持 SOLIDWORKS 开启，使用同一交互式用户执行。

```powershell
cd C:\RemoteB\remote-b-hub
git pull --ff-only
py -3 .\windows-b\probe_parametric_part.py --profile rectangle
```

矩形规格为 100 × 60 mm，拉伸 10 mm。脚本每次生成全新文件名，默认保存到
`REMOTE_B_OUTPUT_DIR`（未设置时为 `D:\codex\output`）；模板使用
`REMOTE_B_PART_TEMPLATE`。可用 `--template` 和 `--output-dir` 单独覆盖。
该测试会创建新文档，并在严格约束和重建检查通过后保存新文件。

成功时应出现 `PARAMETRIC TEST PASSED`，RESULT 中有 width=100、height=60
的尺寸名称、`all_sketches_fully_defined: true`、`rebuild_ok: true` 和实际保存路径及大小。
需在 SOLIDWORKS 中检查尺寸为驱动尺寸、拉伸深度为 10 mm。

矩形通过后再执行圆柱测试（直径 30 mm、拉伸 60 mm）：

```powershell
py -3 .\windows-b\probe_parametric_part.py --profile circle
```

圆柱成功结果应有 diameter=30 的尺寸名称、完全定义和重建成功，并检查拉伸深度。
这些数值是配方要求，尚不是实机验收结论。任一步报错时保留从 Recipe 到完整 traceback
的输出，先修复对应 COM/约束阶段，不要关闭严格模式反复重试。
两个零件通过后再重启原代理，验证经 NAS 的同规格任务链路；不要同时运行多个代理。

## 本地验证

```powershell
py -3 -m unittest discover -s tests -p test_sw_constraints.py -v
```

15 项 mock 回归测试通过：包括属性/方法两种 GetLength、可调用 COM 返回对象、
Select2 跳过管理器、Select4 回退、选择失败不创建尺寸、圆直径尺寸入口。
这些测试不需要安装 SOLIDWORKS，不能代替上述实机验证。

## 参考

- [SOLIDWORKS ISketchSegment.Select2](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISketchSegment~Select2.html)：参数为 Append 和 Mark，已被 Select4 取代。
- [SOLIDWORKS ISketchSegment.Select4](https://help.solidworks.com/2011/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.isketchsegment~select4.html)：第二个参数是 ISelectData。
- [pywin32 dynamic.py](https://github.com/mhammond/pywin32/blob/main/com/win32com/client/dynamic.py)：CDispatch.__call__ 使用默认成员；不能仅按 callable 判断返回接口是否需要再次调用。
