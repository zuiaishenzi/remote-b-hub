"""Windows B task agent: runs only safe, allowlisted operations.
Run inside the interactive Windows login session for SolidWorks COM.
"""
import json
import os
import platform
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ['REMOTE_B_SERVER_URL'].rstrip('/')
TOKEN = os.environ['REMOTE_B_AGENT_TOKEN']
OUTPUT_DIR = Path(os.environ.get('REMOTE_B_OUTPUT_DIR', r'C:\RemoteB\output'))
TEMPLATE = os.environ.get('REMOTE_B_PART_TEMPLATE', '')
if len(TOKEN) < 32:
    raise RuntimeError('REMOTE_B_AGENT_TOKEN must be set')
if not BASE_URL.startswith(('http://', 'https://')):
    raise RuntimeError('Invalid REMOTE_B_SERVER_URL')


def api(method, path, data=None):
    payload = None if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(BASE_URL + path, data=payload, method=method,
             headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.load(res)


def get_sw():
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError('Install pywin32 on PC B to use SolidWorks COM') from exc
    pythoncom.CoInitialize()
    try:
        return win32com.client.GetActiveObject('SldWorks.Application')
    except Exception as exc:
        raise RuntimeError('SolidWorks is not running in this user session') from exc


def execute(operation, params):
    if operation == 'ping':
        return {'message': 'pong from PC B', 'host': socket.gethostname()}
    if operation == 'system_info':
        return {'host': socket.gethostname(), 'os': platform.platform(),
                'python': sys.version.split()[0], 'architecture': platform.machine()}
    if operation == 'solidworks_status':
        sw = get_sw()
        return {'connected': True, 'revision': str(sw.RevisionNumber()), 'visible': bool(sw.Visible)}
    if operation == 'create_blank_part':
        name = params.get('name', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', name):
            raise ValueError('Invalid part name')
        if not TEMPLATE or not Path(TEMPLATE).is_file():
            raise RuntimeError('Set REMOTE_B_PART_TEMPLATE to a valid .prtdot path')
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / (name + '.SLDPRT')
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite existing file: {path}')
        sw = get_sw()
        model = sw.NewDocument(TEMPLATE, 0, 0.0, 0.0)
        if model is None:
            raise RuntimeError('SolidWorks NewDocument returned None')
        # IModelDoc2.SaveAs3: (path, version, options). Options 2 = silent.
        saved = bool(model.SaveAs3(str(path), 0, 2))
        if not saved or not path.exists():
            raise RuntimeError('SolidWorks failed to save part; check dialog, permissions and template')
        return {'saved': str(path), 'bytes': path.stat().st_size, 'part_name': name}
    raise ValueError('Unsupported operation')


def main():
    print('PC B agent started: ' + BASE_URL, flush=True)
    while True:
        try:
            response = api('GET', '/agent/next')
            job = response.get('job')
            if job is None:
                time.sleep(2)
                continue
            print('Executing', job['operation'], job['job_id'], flush=True)
            try:
                answer = {'ok': True, 'value': execute(job['operation'], job['params'])}
            except Exception as exc:
                answer = {'ok': False, 'error': f'{type(exc).__name__}: {str(exc)[:1000]}'}
            print('Result:', 'ok' if answer['ok'] else answer['error'], flush=True)
            api('POST', '/agent/jobs/' + job['job_id'] + '/result', answer)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            print('Connection error:', exc, flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
