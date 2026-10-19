"""Local Codex stdio MCP bridge. Uses the server's authenticated HTTP API.
Requires MCP Python SDK v2: pip install 'mcp>=2,<3'
"""
import json
import os
import urllib.request
from typing import Literal
from mcp.server import MCPServer

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
    """Check whether SolidWorks is running in the B agent's user session. Returns a job id."""
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
    Part operations: boss_extrude, cut_extrude; profiles: rectangle, circle, polygon.
    Assembly: insert .SLDPRT from configured output directory; mates: coincident,
    concentric, parallel, perpendicular, distance, angle by explicit reference plane
    or named entity. Coordinates are millimeters, angles degrees. No arbitrary COM,
    macros or Python. Never overwrites files. Returns job_id to poll computer_b_job.
    Assembly mates are experimental and must be checked in SolidWorks.
    """
    return request('POST', '/api/jobs', {
        'operation': 'sw_recipe', 'params': {'recipe': recipe}
    })


@mcp.tool()
def computer_b_job(job_id: str) -> dict:
    """Retrieve the status and output of an earlier task by job ID. Read-only."""
    return request('GET', '/api/jobs/' + job_id)


if __name__ == '__main__':
    mcp.run()
