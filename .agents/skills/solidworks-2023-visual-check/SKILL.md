---
name: solidworks-2023-visual-check
description: Inspect and perform authorized SOLIDWORKS 2023 GUI modeling through a visible UU or ToDesk remote window using an available computer-use skill. Use for CAD UI verification, dialogs and GUI fallback when recipe tools lack the required feature.
---

# SolidWorks 2023 visual work

Use the installed computer-use skill's APIs and policy. This skill supplies CAD/remote-window
guidance, not a new mouse/keyboard tool. If desktop automation is unavailable, report that limitation.
Do not assume opening UU/ToDesk automatically grants model vision.

Select the returned remote-session window (not the connection manager), activate it, capture a fresh
screenshot and verify that the visible content really is B/SolidWorks before every action sequence.
Remote framebuffer elements are not local accessibility elements. Use coordinates from the latest
screenshot, perform one action, then refresh; old coordinates are invalid after resizing or a dialog.

Use a new unsaved document for a modeling probe, or preserve an existing document as requested.
In SW2023, choose the reference plane, enter sketch mode, draw the required closed profile, add driving
dimensions, verify full definition, exit sketch, create the feature, inspect depth/preview, confirm,
then rebuild and inspect the feature tree. Look for actual failures after each state transition.
Use the modeling skill for parameter contracts and save/result evidence.

Observed workstation behavior: `type_text` into the UU canvas did not reach the remote dimension edit.
After observing/refocusing the actual edit field, Ctrl+A and individual numeric `press_key` calls worked.
Reobserve between inputs and inspect the final value. This is a tested workaround, not a guarantee for
every text field or client version. Never infer dimensions solely from screen pixel size.

Never type terminal commands, scripts or macros into remote terminals, the Run dialog, Explorer address
bars or file dialogs as a shortcut around computer-use limits. Authentication and security/privacy dialogs
must follow the computer-use skill's boundaries. Do not operate an unrelated app visible through UU.

The 2026-10-20 local GUI probe made a new unsaved Ø20×10 mm cylinder on B/SW2023, saw a fully defined
circle sketch, one solid and a boss feature, and no visible error after Ctrl+B. This is a GUI baseline;
it did not verify a saved file, exact gear teeth, assemblies, arbitrary Unicode input, or every CAD operation.
For new work, return what was actually observed, document/save status and remaining engineering checks.
