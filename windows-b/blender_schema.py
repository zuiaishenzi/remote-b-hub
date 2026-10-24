# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared A/NAS/B contract. Full-trust Blender commands are a separate opt-in."""
import ast
import json
import re

ACTIONS = {'status', 'start', 'inspect', 'tool', 'script', 'state', 'resume', 'image'}


def validate_blender_request(params):
    if type(params) is not dict or type(params.get('action')) is not str or params['action'] not in ACTIONS:
        raise ValueError('Invalid Blender action')
    action = params['action']
    extra = {'tool': {'name', 'arguments', 'timeout_seconds'},
             'script': {'code', 'timeout_seconds'},
             'resume': {'pause_id', 'acknowledge_state'}, 'image': {'file'}}.get(action, set())
    if set(params) - ({'action'} | extra):
        raise ValueError('Unexpected Blender parameters')
    timeout = params.get('timeout_seconds', 60)
    if type(timeout) is not int or not 10 <= timeout <= 300:
        raise ValueError('timeout_seconds must be an integer from 10 to 300')
    if action == 'tool':
        if type(params.get('name')) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,79}', params['name']):
            raise ValueError('Provide a command name from computer_b_blender_tools')
        if type(params.get('arguments', {})) is not dict:
            raise ValueError('arguments must be an object')
    if action == 'script':
        code = params.get('code')
        if type(code) is not str or not code.strip() or len(code.encode('utf-8')) > 24000:
            raise ValueError('code must contain 1..24000 UTF-8 bytes')
        try:
            ast.parse(code, filename='<remote-blender-script>')
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise ValueError('Invalid Python script: ' + str(exc)) from exc
    if action == 'resume':
        if type(params.get('pause_id')) is not str or not re.fullmatch('[a-f0-9]{64}', params['pause_id']):
            raise ValueError('Provide the exact current Blender pause_id')
        if params.get('acknowledge_state') is not True:
            raise ValueError('Inspect B and explicitly acknowledge its state')
    if action == 'image':
        name = params.get('file')
        if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}\.(png|jpg|jpeg)', name, re.I):
            raise ValueError('file must be a simple PNG/JPEG name in the Blender output directory')
    try:
        if len(json.dumps(params, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 40000:
            raise ValueError('Blender request too large')
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('Blender parameters must be finite JSON values') from exc
