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

SERVER = os.environ['REMOTE_B_API_URL'].rstrip('/')
TOKEN = os.environ['REMOTE_B_CLIENT_TOKEN']
if len(TOKEN) < 32:
    raise RuntimeError('REMOTE_B_CLIENT_TOKEN must be set')
if not SERVER.startswith(('http://', 'https://')):
    raise RuntimeError('Invalid REMOTE_B_API_URL')


def request(method, path, body=None):
    payload = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(SERVER + path, data=payload, method=method,
            headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


mcp = MCPServer('PC-B-Remote-Tools')


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
                           file: str | None = None, new_file: str | None = None) -> dict:
    """Queue fixed C#/SOLIDWORKS Interop document control, never arbitrary code.
    inspect returns feature/assembly trees and geometry summaries; omit file for active doc.
    Other actions require a simple SLDPRT/SLDASM filename inside B's configured output root.
    open is read-only; rebuild does not save; save_copy requires a NEW same-type filename;
    close refuses modified documents. No existing CAD file is overwritten.
    Requires upgraded NAS and B EXE, plus B's local SOLIDWORKS Interop DLLs.
    """
    params = {'action': action}
    if file is not None:
        params['file'] = file
    if new_file is not None:
        params['new_file'] = new_file
    return request('POST', '/api/jobs', {'operation': 'sw_document', 'params': params})


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
