"""Run local smoke test without Windows or SolidWorks. Requires FastAPI + httpx."""
import os
import json
import sys
import tempfile
from pathlib import Path

os.environ['HUB_A_TOKEN'] = 'a'*64
os.environ['HUB_B_TOKEN'] = 'b'*64
with tempfile.TemporaryDirectory() as directory:
    os.environ['HUB_DB'] = str(Path(directory) / 'smoke.sqlite3')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'linux-server'))
    from fastapi.testclient import TestClient
    from server import app

    client = TestClient(app)
    assert client.get('/health').status_code == 200
    assert client.get('/api/status').status_code == 401
    ah = {'Authorization': 'Bearer ' + 'a'*64}
    bh = {'Authorization': 'Bearer ' + 'b'*64}
    assert not client.get('/api/status', headers=ah).json()['online']
    j = client.post('/api/jobs', headers=ah, json={'operation':'ping'}).json()['job_id']
    fetched = client.get('/agent/next', headers=bh).json()['job']
    assert fetched['job_id'] == j and fetched['operation'] == 'ping'
    assert client.post(f'/agent/jobs/{j}/result', headers=bh,
             json={'ok':True,'value':{'message':'pong'}}).status_code == 200
    assert client.get('/api/jobs/' + j, headers=ah).json()['status'] == 'done'
    assert client.post('/api/jobs', headers=ah,
             json={'operation':'powershell', 'params': {'command':'whoami'}}).status_code == 400
    assert client.post('/api/jobs', headers=bh, json={'operation':'ping'}).status_code == 401
    # New safe SolidWorks create_box operation only accepts bounded, finite dimensions.
    ok_box = {'operation': 'create_box', 'params': {'name': 'Test_Box_001',
              'length_mm': 60, 'width_mm': 40.0, 'height_mm': 20}}
    response = client.post('/api/jobs', headers=ah, json=ok_box)
    assert response.status_code == 200, response.text
    invalid_boxes = [
        {'name': '../bad', 'length_mm': 60, 'width_mm': 40, 'height_mm': 20},
        {'name': 'Test', 'length_mm': 0, 'width_mm': 40, 'height_mm': 20},
        {'name': 'Test', 'length_mm': 60, 'width_mm': 501, 'height_mm': 20},
        {'name': 'Test', 'length_mm': True, 'width_mm': 40, 'height_mm': 20},
        {'name': 'Test', 'length_mm': '60', 'width_mm': 40, 'height_mm': 20},
        {'name': 'Test', 'length_mm': 60, 'width_mm': 40, 'height_mm': 20, 'command': 'whoami'},
    ]
    for params in invalid_boxes:
        response = client.post('/api/jobs', headers=ah, json={'operation': 'create_box', 'params': params})
        assert response.status_code == 400, response.text
    rectangle = {'doc_type': 'part', 'name': 'Test_Part_001', 'operations': [
        {'op': 'boss_extrude', 'plane': 'front', 'depth_mm': 20, 'profile':
            {'type': 'rectangle', 'cx_mm': 0, 'cy_mm': 0,
             'width_mm': 60, 'height_mm': 40}}]}
    valid = client.post('/api/jobs', headers=ah, json={
        'operation': 'sw_recipe', 'params': {'recipe': rectangle}})
    assert valid.status_code == 200, valid.text
    invalid = [dict(rectangle, name='../unsafe'),
               dict(rectangle, operations=[dict(rectangle['operations'][0], op='arbitrary_python')]),
               dict(rectangle, operations=[dict(rectangle['operations'][0], depth_mm=float('inf'))])]
    for item in invalid:
        response = client.post('/api/jobs',
            headers={**ah, 'Content-Type': 'application/json'},
            content=json.dumps({'operation': 'sw_recipe', 'params': {'recipe': item}}))
        assert response.status_code in (400, 422), response.text
    assembly = {'doc_type': 'assembly', 'name': 'Test_Assembly_001',
       'components': [
          {'id':'base','file':'Test_Part_001.SLDPRT','position_mm':[0,0,0]},
          {'id':'top','file':'Test_Part_002.SLDPRT','position_mm':[0,0,25]}],
       'mates':[{'type':'coincident','a':{'component':'base','plane':'front'},
                 'b':{'component':'top','plane':'front'}}]}
    response = client.post('/api/jobs', headers=ah,
        json={'operation': 'sw_recipe', 'params': {'recipe': assembly}})
    assert response.status_code == 200, response.text
    # Strict sketch definition defaults on, with explicit opt-out for legacy tests.
    good = dict(rectangle, allow_underdefined=False)
    response = client.post('/api/jobs', headers=ah,
        json={'operation':'sw_recipe', 'params':{'recipe':good}})
    assert response.status_code == 200, response.text
    bad = dict(rectangle, allow_underdefined='no')
    response = client.post('/api/jobs', headers=ah,
        json={'operation':'sw_recipe', 'params':{'recipe':bad}})
    assert response.status_code == 400, response.text
    # A failed CAD recipe can be revised to a new filename without losing its history.
    job = valid.json()['job_id']
    while True:
        picked = client.get('/agent/next', headers=bh).json()['job']
        if picked['job_id'] == job:
            break
    assert client.post(f'/agent/jobs/{job}/progress', headers=bh,
        json={'stage':'drawing_sketch','step':1}).status_code == 200
    assert client.post(f'/agent/jobs/{job}/result', headers=bh,
        json={'ok':False,'error':'COM operation failed',
              'diagnostics':{'stage':'drawing_sketch','traceback':'demo traceback'}}).status_code == 200
    result = client.get('/api/jobs/'+job, headers=ah).json()
    assert result['progress']['stage'] == 'drawing_sketch'
    assert result['result']['diagnostics']['stage'] == 'drawing_sketch'
    revised = dict(rectangle, name='Test_Part_002')
    newer = client.post(f'/api/jobs/{job}/revise', headers=ah, json={'recipe':revised})
    assert newer.status_code == 200, newer.text
    assert newer.json()['job_id'] != job
    same_name = client.post(f'/api/jobs/{job}/revise', headers=ah, json={'recipe':rectangle})
    assert same_name.status_code == 400
    script = {'operation': 'sw_script', 'params': {'mode': 'execute',
               'code': 'result = {"fixture": True}', 'timeout_seconds': 60}}
    assert client.post('/api/jobs', headers=bh, json=script).status_code == 401
    created = client.post('/api/jobs', headers=ah, json=script)
    assert created.status_code == 200, created.text
    stored = client.get('/api/jobs/' + created.json()['job_id'], headers=ah).json()
    assert stored['request'] == script['params']
    assert 'sw_script' in client.get('/health').json()['capabilities']
    script['params']['code'] = 'if'
    assert client.post('/api/jobs', headers=ah, json=script).status_code == 400
    assert client.post('/api/jobs', headers=ah, json={'operation': 'sw_script',
        'params': {'mode': 'inspect'}}).status_code == 200
    print('PASS: auth, queue, recipe revisions, progress and structured diagnostics')
