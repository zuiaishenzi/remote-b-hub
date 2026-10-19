# FullyDefineSketch 基准参数 COM 类型修复

## 已知事实与本次范围

Windows B / SOLIDWORKS 31.5.0 已能连接 COM 并生成严格的无孔矩形块。
用户随后提交的 100×60×10 mm 机架，在第二步 x=±20 mm 的 Ø8 圆孔草图中，
创建直径尺寸后进入 `FullyDefineSketch`，报类型不匹配
`(-2147352571, ..., None, 6)`；尚未切孔、重建和保存，机构未完成。

本次只修复执行器的 COM 参数，并增加定位检查和偏心圆回归入口。
不重试旧机架任务，不取消严格约束，不把无孔块当机架，不实现或声称已完成齿轮/机构。
**本地类型/逻辑测试和 EXE 打包测试不等于 B 的 SOLIDWORKS 实机验收。**

## 签名与修复

官方 `ISketchManager.FullyDefineSketch` 的第 6、8 个参数分别是
`HorizontalDatumDisp` 和 `VerticalDatumDisp`，类型为对象。
官方 VBA 示例使用 `Nothing`；Python 裸 `None` 可能被封送为 `VT_NULL`，
它与空 `IDispatch` 不同。报错的 arg-error 数字不能单独当作 Python 从 1 起算的参数号。

执行器现在分别传入 `win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)`，
其余尺寸方案与关系选项保持不变。这一改变针对类型问题，不保证自动求解一定成功。
调用不做循环重试，异常后清空选择并失败退出；调用返回值不作为成功凭据，必须重新读取
`GetConstrainedStatus` 并满足 fully_defined。仍欠定义、过定义或状态异常时禁止保存。

圆草图解算后额外读取圆心和半径，按草图坐标核对 `cx_mm`、`cy_mm`、`radius_mm`，
允差 0.01 mm；非有限值、圆心移动或半径不符时失败，不固定圆心、不改变配方绕过问题。
成功结果的 `sketches[].profile_geometry` 返回实际读数。

参考：[官方方法签名](https://help.solidworks.com/2015/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ISketchManager~FullyDefineSketch.html)、
[官方 VBA 示例](https://help.solidworks.com/2019/english/api/sldworksapi/Fully_Define_Underdefined_Sketch_Example_VB.htm)、
[GetCenterPoint2](https://help.solidworks.com/2023/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ISketchArc~GetCenterPoint2.html)。

## B 端最小回归

先停止 EXE 或命令行轮询代理，避免同时操作 SW；保持 SW 已打开。
以下测试创建一个全新偏心圆柱，不修改旧机架；严格检查通过后才保存新文件。
测试直径 8 mm、拉伸 10 mm，逐步覆盖正/负 X 和两个轴都偏离原点的圆心：

```powershell
cd C:\RemoteB\remote-b-hub
git pull --ff-only
py -3 .\windows-b\probe_parametric_part.py --profile offset-circle --cx-mm 20 --cy-mm 0
# 上一项通过后继续；报错则先保留完整输出，停止后续测试。
py -3 .\windows-b\probe_parametric_part.py --profile offset-circle --cx-mm -20 --cy-mm 0
py -3 .\windows-b\probe_parametric_part.py --profile offset-circle
```

最后一项默认圆心为 (20, 12) mm。模板/输出目录与 GUI 不同时，应显式传入
`--template '实际模板路径' --output-dir '实际输出目录'`；命令行测试不会自动读取 GUI 的加密配置。

验收输出应包括 `Executor` 指纹、`VT_DISPATCH(null)` 日志（若需要调用自动全定义）、
真实 fully_defined 状态、`profile_geometry.checked: true`、正确的圆心/半径、
`rebuild_ok: true` 和新文件信息。仍需在 SW 检查尺寸/约束与几何，不仅看保存文件。
这些单圆测试通过后，才以新名称执行机架的凸台/切孔组合回归；它们本身不证明切孔正确。

## 确认 B 实际运行的版本

源码模式输出 `executor_sha256`。新版 EXE 在构建时内嵌源码指纹、Git 提交、构建时间
以及是否包含未提交修改。启动器标题显示指纹前 12 位，启动日志显示完整信息，
任务成功结果的 `value.executor` 或错误的 `diagnostics.executor` 也会带版本。
GitHub 发布的干净构建应有 `working_tree_dirty: false`。

EXE 内嵌代码不会因为 `git pull` 改变。先停止并退出旧 EXE，再从 GitHub Releases
下载新版并替换启动；用户目录里的配置会保留。提交下一条 CAD 测试前检查启动日志的
`source_commit` 和 `executor_sha256`，不能仅根据 traceback 行号判断已部署修复。
