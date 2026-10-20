"""Exercise actual frozen child protocol. Only reads SW if present; never creates CAD."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows-b'))
from script_schema import validate_script_request

with tempfile.TemporaryDirectory(prefix='sw-script-frozen-') as temp:
    folder = Path(temp)
    params = {'mode': 'inspect'}
    (folder/'request.json').write_text(json.dumps(params))
    completed = subprocess.run([sys.argv[1], '--run-sw-script', str(folder)],
        timeout=90, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert completed.returncode == 0
    response = json.loads((folder/'response.json').read_text(encoding='utf-8'))
    assert response['script_sha256'] == validate_script_request(params)
    assert type(response['ok']) is bool
    if not response['ok']:
        assert 'Traceback' in response['traceback']
        assert 'ModuleNotFoundError' not in response['traceback'], response
    print(json.dumps({'frozen_script_protocol': True, 'real_sw_connected': response['ok'],
                      'cad_created': False}))
