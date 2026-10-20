"""Actual MCP SDK/stdio discovery and local planning, with deliberately fake credentials.

No network request and no CAD creation. Requires windows-a/requirements.txt.
"""
import asyncio
import json
from pathlib import Path
import sys
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def main():
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(ROOT/'windows-a/mcp_bridge.py')],
        env={'REMOTE_B_API_URL': 'http://127.0.0.1:1', 'REMOTE_B_CLIENT_TOKEN': 'mcp-smoke-test-' + 'x'*32})
    async with Client(parameters) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert {'computer_b_modeling_skills', 'computer_b_plan_part', 'computer_b_review_part'} <= names
        document_tool=next(tool for tool in listed.tools if tool.name=='computer_b_sw_document')
        assert 'dimension_names' in document_tool.input_schema['properties']
        result = await client.call_tool('computer_b_modeling_skills', {})
        assert not result.is_error
        interop=await client.call_tool('computer_b_modeling_skills',{'skill':'solidworks-2023-interop'})
        assert not interop.is_error
        assert '58787e2cefdcc03aebc15a51bd52ba151f3969d4' in str(interop)
        for template in ('box', 'cylinder', 'tube', 'two_hole_plate'):
            result = await client.call_tool('computer_b_plan_part', {
                'template': template, 'parameters': {}, 'name': 'MCP_Smoke_' + template})
            assert not result.is_error, result
        bad = await client.call_tool('computer_b_plan_part', {
            'template': 'tube', 'parameters': {'inner_radius_mm': 20}, 'name': 'MCP_Bad'})
        assert bad.is_error
        bad_dimension=await client.call_tool('computer_b_sw_document',{
            'action':'inspect','dimension_names':['D1@Sketch1@Part']})
        assert bad_dimension.is_error
        print(json.dumps({'real_stdio': True, 'tools': sorted(names), 'plans': 4, 'invalid_plan_rejected': True}))


if __name__ == '__main__':
    asyncio.run(main())
