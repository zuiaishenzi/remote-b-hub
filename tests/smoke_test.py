"""Run local smoke test without Windows or SolidWorks. Requires FastAPI + httpx."""
import os
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
    print('PASS: auth, queue, agent fetch/result, allowlist')
