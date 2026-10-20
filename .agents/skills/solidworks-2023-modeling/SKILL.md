---
name: solidworks-2023-modeling
description: Plan and verify SOLIDWORKS 2023 parts and basic assemblies through remote-b-hub's pc-b MCP. Use for parameterized modeling, constrained sketches, recipe diagnosis and engineering result checks on Windows B.
---

# SolidWorks 2023 modeling

Use the project executor as the capability boundary. This is a remote adaptation informed by
LTGOz/solidworks-agent-skill at commit 693386f5d76cca57ee3d80359c3b19128660366c;
its local COM scripts and upstream recipes are not interchangeable with pc-b recipes.
Read [the source and compatibility notes](references/compatibility.md) when choosing a workflow.

## Plan and execute

1. Check `computer_b_status` and submit `computer_b_solidworks_status`; read the returned job.
   SW 2023 is revision 31.x. A source-code version/fingerprint is not the SW version.
   If B is offline, do not accumulate modeling jobs while waiting for it.
2. Separate specified dimensions from assumptions. Resolve dimensions that determine the design.
   All recipe distances are mm; Python COM converts to meters. Do not convert mm twice.
3. Call `computer_b_modeling_skills()` to discover the installed adapter and real capabilities.
   For box/cylinder/tube/two-hole plate, use `computer_b_plan_part(template, parameters, name)`.
   This returns a validated recipe and explicit assumptions, without creating CAD or claiming a model exists.
   Check `execution_ready` and `validation`: the two-hole plate is currently blocked by a real
   rectangle constraint failure. Do not submit that template until the executor is fixed and tested.
   A box passed once, but the later plate's identical base remained under-defined; report this
   intermittent rectangle constraint limitation rather than promising reliable completion.
   Other supported designs may use a full explicit recipe; consult [recipe rules](references/recipes.md).
4. Submit the reviewed recipe with `computer_b_sw_recipe`, then read `computer_b_job`.
   New names only; never overwrite an existing model. Keep strict constraints enabled.
5. Call `computer_b_review_part(template, parameters, name, job_id)` to fetch and compare the real job result
   to the design contract. Geometry volume listed by the planner is an expectation, not a measurement.
   Verify actual extrusion depth, solid topology/volume and saved document in SW or with supported
   inspection tooling; missing evidence remains explicitly unverified.

## Failure handling

Read request, progress, result, diagnostics and full traceback before deciding on a revision.
Do not repeat an unchanged COM failure or change dimensions to conceal it. A code defect requires
an executor fix plus regression tests before using that interface again.
For a correctable design issue, submit a full changed recipe via `computer_b_revise_recipe`, use a new
name, and retain parent job ID. Limit each failed task to three different design revisions.
Never silently enable allow_underdefined or replace required engineering features with visual approximations.

## Capability boundaries

- Current deterministic operations: boss_extrude/cut_extrude with centered rectangles or circles,
  explicit driving dimensions and strict sketch checks; circle offsets are explicitly constrained.
- Basic assembly insertion/mates exist but require task-specific real mate and rebuild acceptance.
  File placement alone does not prove constrained assembly behavior.
- Revolve, fillet, chamfer, patterns, equations, exact involute teeth and gear mechanical mates in
  an upstream skill do not add those operations to this executor. Report the missing capability.
- For geometry not supported by recipes, explain the gap. GUI work can be selected if appropriate
  and authorized, using the companion solidworks-2023-visual-check skill and an available computer-use tool.
- A successful job must have an actual saved path and nonzero file size, expected feature count,
  each sketch fully defined, and a successful rebuild. Do not invent job IDs or test results.

## Evidence to return

Report the real job ID/status, actual path/bytes, relevant driving dimensions, sketch checks,
feature/rebuild evidence, revision count, and any unverified dimension, geometry, assembly or motion requirement.
Upstream authors' tests are not this workstation's tests. Consult `docs/solidworks-skills.md`
in the project for the application's acceptance record and deployment steps.
