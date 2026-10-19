"""Local HTTP end-to-end: real Uvicorn process + agent process + task result.
No Windows or SolidWorks needed for ping; uses real HTTP and auth.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get(method, base, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, method=method, data=data,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=4) as resp:
        return json.load(resp)


with tempfile.TemporaryDirectory() as tmp:
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        port = s.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    a, b = 'a'*64, 'b'*64
    server_env = {**os.environ, 'HUB_A_TOKEN':a, 'HUB_B_TOKEN':b, 'HUB_DB': str(Path(tmp)/'jobs.sqlite3')}
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', str(port)],
      cwd=ROOT/'linux-server', env=server_env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    agent = None
    try:
        for _ in range(50):
            if server.poll() is not None:
                raise RuntimeError('Server died: ' + str(server.stderr.read()))
            try:
                get('GET', base, '/health', a)
                break
            except OSError:
                time.sleep(0.1)
        agent_env = {**os.environ, 'REMOTE_B_SERVER_URL':base, 'REMOTE_B_AGENT_TOKEN':b}
        agent = subprocess.Popen([sys.executable, '-u', str(ROOT/'windows-b'/'agent.py')], env=agent_env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        r = get('POST',base,'/api/jobs',a,{'operation':'ping'})
        for _ in range(40):
            j = get('GET', base, '/api/jobs/'+r['job_id'],a)
            if j['status'] in ('done','error'):
                break
            time.sleep(0.25)
        assert j['status'] == 'done', j
        assert j['result']['value']['message'] == 'pong from PC B', j
        print('PASS: real HTTP server + agent loop + ping result')
    finally:
        if agent is not None:
            agent.terminate()
            agent.wait(timeout=5)
        server.terminate()
        server.wait(timeout=5)
