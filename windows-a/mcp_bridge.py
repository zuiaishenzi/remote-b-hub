"""Local Codex stdio MCP bridge. Uses the server's authenticated HTTP API.
Requires MCP Python SDK v2: pip install 'mcp>=2,<3'
"""
import json
import os
import urllib.request
from typing import Literal
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from relay_client import RelayClient
from cad_skills import catalog, plan_part, review_part
import uuid

from mcp_connection import load_connection
SERVER, TOKEN = load_connection()


def request(method, path, body=None):
    payload = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(SERVER + path, data=payload, method=method,
            headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


mcp = MCPServer('PC-B-Remote-Tools')


def blender_job(params):
    from blender_schema import validate_blender_request
    try:
        validate_blender_request(params)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return request('POST', '/api/jobs', {'operation': 'blender_control', 'params': params})


@mcp.tool()
def computer_b_blender_tools(name: str | None = None) -> dict:
    """Read the pinned RFingAdam Blender command catalog; pass a name for full JSON schema.
    Local discovery only, not proof of runtime support. Commands execute on B through
    computer_b_blender_command. AI/asset integrations need their own setup/credentials.
    """
    from blender_control import catalog
    try:
        return catalog(name)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def computer_b_blender_status() -> dict:
    """Check B's authenticated Blender bridge without starting Blender. Poll computer_b_job.
    B agent must be online, NAS/B upgraded. Separate from SolidWorks COM/status.
    """
    return blender_job({'action': 'status'})


@mcp.tool()
def computer_b_start_blender() -> dict:
    """Start Blender on B with bundled authenticated bridge; reuse a connected session.
    Never kills an existing Blender or opens duplicate instances. Existing Blender without
    bridge requires enabling the exported add-on on B. Poll computer_b_job.
    """
    return blender_job({'action': 'start'})


@mcp.tool()
def computer_b_blender_scene() -> dict:
    """Read actual B Blender scene/path/dirty flag/objects/modifiers/units (bounded to 80).
    May auto-start if B settings allow. Does not save or modify the scene. Poll the job.
    """
    return blender_job({'action': 'inspect'})


@mcp.tool()
def computer_b_blender_command(name: str, arguments: dict | None = None, timeout_seconds: int = 60) -> dict:
    """Run a pinned upstream Blender command on B, with local full-trust opt-in.
    First query computer_b_blender_tools(name) for parameter schema. Full user rights,
    NOT sandboxed. May modify/delete/save; only do what user requested. No automatic
    retries. Timeout/disconnect pauses Blender controls; inspect state/late receipt.
    Upstream rotations have inconsistent conventions: inspect schema/code or use bpy.
    Return is only job_id; poll computer_b_job for actual results/traceback.
    """
    from blender_control import catalog
    try:
        catalog(name)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return blender_job({'action': 'tool', 'name': name, 'arguments': arguments or {}, 'timeout_seconds': timeout_seconds})


@mcp.tool()
def computer_b_blender_script(code: str, timeout_seconds: int = 60) -> dict:
    """Run full-trust bpy Python on B's Blender MAIN THREAD, only when B enables it.
    Namespace: bpy, snapshot(), output_dir, log(); set JSON dict result. Coordinates
    are Blender units, angles radians; inspect scene.unit_settings before mm conversion.
    Does not automatically save. Prefer separate new scene and NEW output file.
    Timeout/disconnect leaves Blender open and pauses commands; do not retry blindly.
    Poll computer_b_job; inspect before/after/log_tail/traceback and real saved file evidence.
    """
    return blender_job({'action': 'script', 'code': code, 'timeout_seconds': timeout_seconds})


@mcp.tool()
def computer_b_blender_state() -> dict:
    """Read Blender pause ID, audit and any late terminal receipt without contacting bpy.
    can_resume means a terminal receipt exists or the old process exited, not model validity. Poll the job.
    """
    return blender_job({'action': 'state'})


@mcp.tool()
def computer_b_resume_blender(pause_id: str, acknowledge_state: bool) -> dict:
    """Resume exact Blender pause after reading late result and inspecting scene/B.
    Requires B opt-in and terminal receipt or confirmed old process exit; never cancels running bpy.
    Model correctness is not implied. Do not repeat failed script unchanged. Poll job.
    """
    return blender_job({'action': 'resume', 'pause_id': pause_id, 'acknowledge_state': acknowledge_state})


@mcp.tool()
def computer_b_blender_image(file: str) -> dict:
    """Upload an existing PNG/JPEG from B's configured Blender output directory.
    Simple filename only; requires B Blender image opt-in. Does not capture desktop.
    Render/save explicitly first, then poll this job and download/open artifact on A.
    """
    return blender_job({'action': 'image', 'file': file})


@mcp.tool()
def computer_b_modeling_skills(skill: str | None = None) -> dict:
    """Read reviewed SolidWorks 2023 skills, template parameters and capability limits.
    Local knowledge only; does not connect to B or claim real CAD acceptance.
    """
    try:
        return catalog(skill)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def computer_b_plan_part(template: Literal['box', 'cylinder', 'tube', 'two_hole_plate'],
                         parameters: dict, name: str) -> dict:
    """Compile mm parameters into a strictly validated recipe, reporting all defaults.
    Local preflight only. Submit the returned recipe using computer_b_sw_recipe;
    poll the actual job and use computer_b_review_part. No arbitrary code/macros.
    """
    try:
        return plan_part(template, parameters, name)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def computer_b_review_part(template: Literal['box', 'cylinder', 'tube', 'two_hole_plate'],
                           parameters: dict, name: str, job_id: str) -> dict:
    """Fetch a REAL job and compare its request, features, sketches, dimensions and save
    evidence against the design contract. Reports missing evidence explicitly.
    A passing process review does not prove actual depth, topology or motion.
    """
    try:
        identity = str(uuid.UUID(job_id))
        plan_part(template, parameters, name)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return review_part(template, parameters, name, request('GET', '/api/jobs/' + identity))


@mcp.tool()
def computer_b_status() -> dict:
    """Check whether PC B agent is online. Read-only."""
    return request('GET', '/api/status')


@mcp.tool()
def computer_b_ping() -> dict:
    """Submit a harmless ping task to PC B. Returns a job id."""
    return request('POST', '/api/jobs', {'operation': 'ping'})


@mcp.tool()
def computer_b_system_info() -> dict:
    """Get basic OS information from PC B asynchronously. Returns a job id."""
    return request('POST', '/api/jobs', {'operation': 'system_info'})


@mcp.tool()
def computer_b_solidworks_status() -> dict:
    """Check SolidWorks in B's user session. The desktop agent can auto-start SW
    when enabled in its settings. Returns a job id; poll computer_b_job.
    """
    return request('POST', '/api/jobs', {'operation': 'solidworks_status'})


@mcp.tool()
def computer_b_create_blank_part(name: str) -> dict:
    """Create a blank SLDPRT on PC B using its configured SolidWorks template. Never overwrites files. Returns a job id."""
    return request('POST', '/api/jobs', {'operation': 'create_blank_part', 'params': {'name': name}})


@mcp.tool()
def computer_b_create_box(name: str, length_mm: float, width_mm: float, height_mm: float) -> dict:
    """Create a new rectangular SOLIDWORKS solid (mm) on PC B. Never overwrites files.
    Dimensions must each be 1..500 mm. Returns a job_id; poll computer_b_job.
    The initial sketch is geometric, not fully dimension-constrained.
    """
    return request('POST', '/api/jobs', {
        'operation': 'create_box',
        'params': {'name': name, 'length_mm': length_mm,
                   'width_mm': width_mm, 'height_mm': height_mm}
    })


@mcp.tool()
def computer_b_sw_recipe(recipe: dict) -> dict:
    """Execute a restricted SolidWorks modeling plan (part or assembly) on PC B.
    Strict part operations: boss_extrude, cut_extrude; profiles: rectangle, circle.
    Polygon is legacy-only and is rejected in strict mode. Prefer computer_b_plan_part.
    Assembly: insert .SLDPRT from configured output directory; mates: coincident,
    concentric, parallel, perpendicular, distance, angle by explicit reference plane
    or named entity. Coordinates are millimeters, angles degrees. No arbitrary COM,
    macros or Python. Never overwrites files. Returns job_id to poll computer_b_job.
    Sketches default to strict fully-defined mode with explicit driving dimensions.\n    Legacy allow_underdefined=true bypasses strict enforcement (not recommended).\n    Assembly mates are experimental and must be checked in SolidWorks.
    """
    return request('POST', '/api/jobs', {
        'operation': 'sw_recipe', 'params': {'recipe': recipe}
    })


@mcp.tool()
def computer_b_revise_recipe(job_id: str, recipe: dict) -> dict:
    """Revise a completed/failed SolidWorks job using a FULL corrected recipe.
    Always choose a NEW output name; no overwrite. Returns new job id.
    Read the parent job's diagnostics and request first. Do not repeat
    unchanged failures or weaken constraints without user approval.
    """
    return request('POST', '/api/jobs/' + job_id + '/revise', {'recipe': recipe})


@mcp.tool()
def computer_b_job(job_id: str) -> dict:
    """Retrieve the status and output of an earlier task by job ID. Read-only."""
    return request('GET', '/api/jobs/' + job_id)


@mcp.tool()
def computer_b_sw_document(action: Literal['inspect', 'open', 'rebuild', 'save_copy', 'close'],
                           file: str | None = None, new_file: str | None = None,
                           dimension_names: list[str] | None = None) -> dict:
    """Queue fixed C#/SOLIDWORKS Interop document control, never arbitrary code.
    inspect returns feature/assembly trees and geometry summaries; omit file for active doc.
    Other actions require a simple SLDPRT/SLDASM filename inside B's configured output root.
    open is read-only; rebuild does not save; save_copy requires a NEW same-type filename;
    close refuses modified documents. No existing CAD file is overwritten.
    Requires upgraded NAS and B EXE, plus B's local SOLIDWORKS Interop DLLs.
    inspect optionally accepts up to 20 dimension_names like D1@Sketch1 (not
    the document-qualified full name). Returns actual system values, never edits them.
    Length system values are meters; angle values are radians. Do not assume all are mm.
    """
    params = {'action': action}
    if file is not None:
        params['file'] = file
    if new_file is not None:
        params['new_file'] = new_file
    if dimension_names is not None:
        params['dimension_names'] = dimension_names
    from control_schema import validate_document_request
    try:
        validate_document_request(params)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return request('POST', '/api/jobs', {'operation': 'sw_document', 'params': params})


@mcp.tool()
def computer_b_cad_state() -> dict:
    """Read pause ID and old helper process state without calling SW COM.
    Works while CAD is paused. Poll computer_b_job. can_resume only proves the
    old caller exited, not that the model is valid or SW commands have finished.
    """
    return request('POST', '/api/jobs', {'operation': 'cad_control', 'params': {'action': 'state'}})


@mcp.tool()
def computer_b_start_solidworks() -> dict:
    """Explicitly start SW in B's logged-in session, even if auto-start is off.
    B agent must already be online. Does not start an offline agent, kill SW,
    close documents or bypass a CAD pause. Existing SW instance is reused.
    Runs in a supervised helper; timeout leaves CAD paused and returns caller PID.
    Returns job ID; poll computer_b_job and confirm connected/revision.
    """
    return request('POST', '/api/jobs', {'operation': 'cad_control', 'params': {'action': 'start'}})


@mcp.tool()
def computer_b_resume_cad(pause_id: str, acknowledge_state: bool) -> dict:
    """Recover the EXACT current pause from A after inspecting the failure, CAD
    state and available screenshot. User has authorized A recovery. B requires
    trusted script control enabled. Never force unlock a live/unknown caller.
    Pass pause_id from computer_b_cad_state and acknowledge_state=true after
    assessment; stale IDs are rejected. Does not retry the failed job or save
    a model. Poll job; then inspect SW session before further editing.
    """
    from cad_control_schema import validate_cad_control
    params = {'action': 'resume', 'pause_id': pause_id, 'acknowledge_state': acknowledge_state}
    try:
        validate_cad_control(params)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return request('POST', '/api/jobs', {'operation': 'cad_control', 'params': params})


@mcp.tool()
def computer_b_sw_session() -> dict:
    """Read B's actual active SW document, modified flag and bounded feature list.
    Requires upgraded NAS/B. Does not rebuild/save, no script opt-in needed.
    Returns job_id: poll computer_b_job; no active document is a valid result.
    """
    return request('POST', '/api/jobs', {'operation': 'sw_script', 'params': {'mode': 'inspect'}})


@mcp.tool()
def computer_b_sw_script(code: str, timeout_seconds: int = 60) -> dict:
    """Execute full-trust Python COM on B, ONLY when locally enabled on B.
    Same Windows user rights, NOT a sandbox. Available variables: sw, model (may
    be None), read(obj, member) for COM property/method reads, snapshot(), log(),
    output_dir, part_template, assembly_template. Assign JSON dict to result.
    API lengths use meters, angles radians. Never overwrite/close unsaved work
    without authorization. Inspect first; execute one reviewable step; then
    verify constraints, geometry, rebuild, saved paths/sizes explicitly.
    No auto-save, no inferred engineering acceptance. Max 24KB UTF-8 Python.
    Poll job for before/after snapshots, log and full failure traceback.
    Timeout pauses subsequent CAD; use CAD state and safe A recovery after caller exits. Never
    retry unchanged errors; do not call known broken interfaces repeatedly.
    Screenshots remain a separate opt-in tool. No generic desktop input here.
    """
    from script_schema import validate_script_request
    params = {'mode': 'execute', 'code': code, 'timeout_seconds': timeout_seconds}
    try:
        validate_script_request(params)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return request('POST', '/api/jobs', {'operation': 'sw_script', 'params': params})


@mcp.tool()
def computer_b_screenshot() -> dict:
    """Queue a SOLIDWORKS-window screenshot. Requires local opt-in on B and NAS attachment API.
    Returns job_id; poll the job, then list/download its artifacts. Never captures full desktop.
    """
    return request('POST', '/api/jobs', {'operation': 'screenshot'})


@mcp.tool()
def computer_b_artifacts(job_id: str) -> dict:
    """List protected screenshot attachments for a real job. Images expire after 48 hours."""
    return request('GET', '/api/jobs/' + job_id + '/artifacts')


@mcp.tool()
def computer_b_get_artifact(artifact_id: str) -> dict:
    """Download a protected screenshot to a real local file on A, verifying size/type/hash.
    The caller must explicitly open the returned downloaded path with an image-reading tool.
    This dictionary alone does not give the model vision access.
    """
    return RelayClient(SERVER, TOKEN).download(artifact_id)


if __name__ == '__main__':
    mcp.run()
