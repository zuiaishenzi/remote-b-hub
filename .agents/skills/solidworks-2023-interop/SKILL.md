---
name: solidworks-2023-interop
description: Inspect and edit SolidWorks 2023 models through remote-b-hub using fixed C# inspection or the locally enabled Python COM script channel. Use for named dimensions, feature trees and stepwise remote CAD editing.
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

## Stepwise Python COM editing

For edits outside recipe capabilities, use `computer_b_sw_session` and poll its job to identify
the actual active document. Check `computer_b_system_info` capabilities: B must have the new
executor and `allow_sw_scripts=true`. If NAS rejects `sw_script`, upgrade NAS before submitting edits.

`computer_b_sw_script(code, timeout_seconds=60)` runs full-trust Python with B user's rights;
the B operator enables this separately. It is not a sandbox or a read-only API.
The script gets `sw`, active `model` (possibly None), `read(obj, member)` for callable/property COM
differences, `snapshot()`, `log()`, `output_dir`, `part_template`, `assembly_template`.
Assign a JSON dictionary to `result`; prefer small, reviewable edits followed by explicit checks.
Use existing user authorization for editing, but do not overwrite files or discard unsaved work
outside that scope. No automatic save is performed. SW lengths are meters and angles radians.

For a first connection test, submit only `result = snapshot()`; verify the real job before editing.
Read before/after snapshots, log, traceback and script SHA256 from the actual result. A done job
proves script execution only. Separately measure geometry, check constraints/rebuild, and record
the actual saved path and byte size. Use fixed C# inspection for assembly/component/body details
and named dimension values, plus opt-in screenshots when needed.

On timeout or missing helper response, B pauses subsequent CAD tasks and keeps SW alive.
Do not retry: the COM call may still be running. Use computer_b_cad_state to inspect the current pause and helper PID. Once the caller
exited and the current state is assessed, A can use computer_b_resume_cad with that pause_id
and acknowledge_state=true; no B-local stop/click is required. Live/unknown callers and stale
pause IDs must not be bypassed. B-local recovery remains available.
The script channel adds API flexibility; it does not prove gear accuracy or provide mouse/keyboard control.


## A-side lifecycle tools

`computer_b_start_solidworks` explicitly starts/connects SW in B's existing login session,
even when auto-start is off. B agent must already be online and CAD must not be paused.
It does not close documents or terminate processes. Poll the real job for connected/revision.

`computer_b_cad_state` works while paused without SW COM. Read the original failure and
available screenshot, check helper_running/can_resume, then recover only the exact pause_id
with `computer_b_resume_cad(pause_id, acknowledge_state=true)` when A recovery is authorized.
After recovery inspect the SW session before edits; never retry the old script unchanged.
