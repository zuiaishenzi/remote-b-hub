---
name: solidworks-2023-interop
description: Inspect named SolidWorks 2023 model dimensions and document geometry through remote-b-hub's fixed C# Interop controller. Use for checking real dimension values, feature trees and C# API compatibility; not arbitrary script execution.
---

# SolidWorks 2023 Interop inspection

This reviewed adapter draws on AngelSix/SolidDNA at commit
`58787e2cefdcc03aebc15a51bd52ba151f3969d4`. It does not install the entire SDK,
its older reference DLLs, an add-in or ScriptRunner. Read
[the compatibility and source notes](references/angelsix.md) before extending C# control.

## Inspect a real model

1. Check B online and SW COM revision 31.x. Use the installed NAS/B protocol:
   a rejected `sw_document` request means the service needs upgrading, not that a model was inspected.
2. For a managed file already open on B, call `computer_b_sw_document` with `action="inspect"`,
   `file="ActualName.SLDPRT"`, and optional `dimension_names=["D1@草图1"]`.
   Omit file only when inspecting the active document is explicitly intended.
3. Use actual dimension/feature names from the task result or inspected document. `IDimension.FullName`
   may include a third document segment; `IModelDoc2.Parameter` needs `D1@Feature`, so keep the first
   two segments. A selection label and a parameter's complete identity are different concepts.
4. Poll the real job. Examine each requested dimension: an `error` row is missing evidence even if
   the inspection task is done. The read-only query never changes a dimension to make a test pass.
5. `system_value` uses SW system units: lengths in meters and angles in radians. Determine the
   dimension's meaning from the design contract; only then convert to mm or degrees.
6. Check feature tree, solid bodies, measured mass properties and `inspection_warnings` separately.
   Bounding boxes are approximate, theoretical template volume is not measured volume, and a
   dimension query does not prove topology, assembly freedom or motion.

## Compatibility and failures

The controller compiles against B's own SolidWorks.Interop.sldworks.dll from SW2023 api/redist.
Its program entry point is STA. Keep fixed actions and typed request validation; do not turn
upstream examples into a remote C#/PowerShell/macro evaluator.
Model this knowledge as API guidance, not proof of an added revolve/fillet/pattern operation.
The new named-dimension path has schema, C# compile and controlled test-double coverage;
real SW2023 COM acceptance must be recorded after upgraded NAS and B are running.
Do not repeat a COM defect unchanged; preserve job ID and complete traceback.
