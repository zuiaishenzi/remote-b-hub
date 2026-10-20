# SolidWorks 2023 建模技能

适用：SOLIDWORKS 2023，COM revision 31.x。此升级增加经过审阅的建模知识、确定性参数模板和任务复核，
由 A 端 Codex 规划，B 端现有白名单执行器建模。没有嵌入另一个大模型或第三方任意宏执行器。

## 来源与适配

参考 [LTGOz/solidworks-agent-skill](https://github.com/LTGOz/solidworks-agent-skill)，
固定提交 `693386f5d76cca57ee3d80359c3b19128660366c`，MIT 授权。
许可文本保存在 `.agents/skills/solidworks-2023-modeling/references/upstream-LICENSE.txt`。
上游面向 SW2023，但使用本地 COM 脚本和另一套 JSON 格式；上游作者的测试不是本站实测。
本项目仅吸收单位、约束、特征顺序和结果检查等知识，重写为当前 pc-b 接口流程。
没有执行或捆绑上游 COM 桥、宏回放、自动试错脚本及其 DFM 依赖。
另检查了 delancy827/solidworks-skills（偏 SW2024）与 wzyn20051216/solidworks-automation-skill，均未直接采用。

两项技能：

- `solidworks-2023-modeling`：状态检查、参数规划、严格配方、失败定位、有限设计修订与结果验收。
- `solidworks-2023-visual-check`：在已配置的 UU/ToDesk 画面上，借助可用的 computer-use 检查尺寸、特征与重建。
  它不会自行安装远控，也不会让仅有文字工具的模型自动获得画面。

## A 端使用

1. 下载新版 [RemoteBClient.exe](https://github.com/zuiaishenzi/remote-b-hub/releases/latest)，保持原有 A Token/NAS/工作目录配置。
2. 点击“建模技能”，选择模板，查看并修改毫米参数和全新文件名。先“生成并校验”，确认实际使用的默认值。
3. “提交 B”会先检查 B 在线状态，再提交现有 `sw_recipe`；任务 ID 与日志显示在主窗口。
4. 完成后保留相同模板、参数和文件名，点击“复核主窗口任务 ID”。复核会从 NAS 获取真实任务，比较请求、
   保存路径、文件大小、特征/草图数量、驱动尺寸、圆的已求解坐标与重建结果。错误保留 diagnostics/traceback。
5. 点击“安装到工作目录”，将两项技能安装进已配置目录的 `.agents/skills`。用户修改过的技能不会被覆盖，
   路径穿越符号链接或 junction 会被拒绝。重新开始 Codex 会话后发现项目技能。

源码用户执行 `git pull --ff-only` 后重启 pc-b MCP/Codex。
已修改工作文件时先保存自己的改动，不强制覆盖。桥接 Python 依赖：`pip install -r windows-a/requirements.txt`。
此版本提供 16 个工具，其中新增：

- `computer_b_modeling_skills(skill?)`：读取经过审阅的技能、版本、模板及能力边界。
- `computer_b_plan_part(template, parameters, name)`：本地预检，返回 recipe、默认值和实测状态，不创建 CAD。
- `computer_b_review_part(template, parameters, name, job_id)`：读取真实任务再复核，不接受调用者伪造的任务结果。

新增模板/MCP 不要求 NAS 新接口；使用既有 `sw_recipe` 即可。本次在线 NAS 对 `sw_document` 请求返回 HTTP 400，
所以没有获得 C# 实体数量、实际体积等检查证据；需要该接口时另按脚本控制升级文档同步 NAS 和 B。
图片传输需要 B 显式启用截图及支持附件的 NAS；实时视频仍需用户自行配置 UU/ToDesk，本次不增加隧道。

## 模板及限制

| 模板 | 默认参数（mm） | 状态 |
| --- | --- | --- |
| box | 100×60×10 | 一次建模通过；后续相同矩形基底出现欠定义，可靠性仍有限 |
| cylinder | R10、深10、圆心(0,0) | 中心圆及偏心圆均实测保存 |
| tube | 外R15、内R10、深10 | 修订一次后保存；基准面切除使用 reverse=true |
| two_hole_plate | 100×60×10、孔R4、孔距40 | 草稿可预检；因实测失败，应用禁止自动提交 |

圆管/双孔板的切除草图位于原始前视基准面，切入实体需要 `reverse=true`。
首个圆管任务缺少该方向，第二步切除返回空特征；仅修改方向、换新文件名，通过 revise 接口提交一次后成功。
模板已固定为该实测方向。不能据此假定其它基准面、任意切除或装配方向也已验证。

`execution_ready` 代表模板未被已知失败阻断，不保证任意参数或任何 B 执行器都能完成。
`expected_volume_mm3` 是解析理论体积，`volume_is_measured=false`。
复核通过仅代表任务证据符合契约，仍返回 `engineering_validation_complete=false`，并列出真实深度、拓扑/体积、
重新打开已保存文件等未验证事项。精确渐开线、圆周阵列、齿轮机械配合仍不支持；不得将示意轮廓称为精确传动。

## 2026-10-20 实机验收

环境连接任务 `1f9010ee-d92e-4d47-9851-67b6998ba49d` 为 done，revision `31.5.0`。
B 为 frozen 执行器，源码提交 `d0e93cce0e3bf62706477f8186f9220096fa5235`，
指纹 `b83993b4db7aa3c505cfe115d4c7a59f90aa768c3eeb875ade41da96d4e37e8c`。

所有路径前缀为 `D:\codex\output\`，未覆盖旧文件。

| 结果 | 任务 ID | 实际文件 | 字节 | 修订 |
| --- | --- | --- | ---: | ---: |
| 长方体 done | ed148d0e-bfde-4f2c-bb3d-945bae72ed78 | Skill_box_c84efaa5b4.SLDPRT | 63788 | 0 |
| 圆柱 done | 5fbd2be8-4f53-443d-8df2-b487b3fdd1da | Skill_cylinder_e14068bfc1.SLDPRT | 81294 | 0 |
| 偏心圆 done，R4、cx20、cy0、深10 | 4265028a-3468-4c1b-90ed-e621860d5753 | Skill_cylinder_5271034ada.SLDPRT | 91776 | 0 |
| 圆管首版 error | b33ac3a2-c20e-48f4-98a6-c01deee8430a | 未保存 | — | 0 |
| 圆管修订 done | e0340483-3b70-423b-9c09-7f53ab01f841 | Skill_tube_rev1_e737e190b0.SLDPRT | 97551 | 1 |
| 双孔板 error | c233d3f4-cf5a-4474-8a95-d3cdb4dfcc5f | 未保存，尚未切孔 | — | 0 |

成功任务的驱动尺寸、各草图 fully_defined/status_code=3、预期特征数及 rebuild_ok 均经复核。
双孔板在第一步矩形宽高尺寸创建后，`FullyDefineSketch` 返回0，但草图仍欠定义，
报错位于运行版本 `sw_constraints.py:234`（调用来源 `sw_recipe.py:129`）。
没有重复调用该失败接口，也没有关闭严格约束或改小尺寸掩盖问题。
下一步应在 B 运行版本中定位矩形原点/对角线关系、几何推断状态，明确添加位置关系，并实测后解除模板阻断。

另有启动失败任务 `14a70412-cd51-4f02-89d0-fd764cb0b116`：SW 未运行时，旧 B 的
`desktop_worker.py:46` WMI GetObject 报 `-2147221020`。用户手动打开 SW 后连接成功。
本次没有宣称修复该自动启动缺陷；当前请先手动打开 SW2023。

本地验证包含技能格式、参数/几何预检、错误结果不能伪装成功、安装保护，以及真实 MCP SDK stdio 工具发现/调用。
打包验证包括 A EXE 内置两项技能、隐藏 GUI 打开技能窗口/生成模板/安装、DPAPI 和退出；B 回归与 HTTP 测试另行保留。
这些测试不模拟真实 CAD 结果。测试脚本 `scripts/verify-modeling-skills.py` 默认仅预检；
显式 `--execute` 会创建新零件，首次失败即停，无自动重试。已阻断模板禁止执行。
