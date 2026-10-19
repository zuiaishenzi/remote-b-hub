"""A-side authenticated HTTP and bounded image download; shared by GUI and MCP."""
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request


class RelayClient:
    def __init__(self, server, token):
        self.server = server.rstrip('/')
        self.token = token

    def request(self, method, path, body=None):
        payload = None if body is None else json.dumps(body).encode('utf-8')
        request = urllib.request.Request(self.server + path, data=payload, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)

    def download(self, artifact_id, directory=None):
        if not re.fullmatch(r'[0-9a-f]{48}', artifact_id):
            raise ValueError('Invalid artifact ID')
        request = urllib.request.Request(self.server + '/api/artifacts/' + artifact_id,
                                        headers={'Authorization': 'Bearer ' + self.token})
        with urllib.request.urlopen(request, timeout=25) as response:
            mime = response.headers.get('Content-Type', '').split(';')[0]
            content = response.read(5 * 1024 * 1024 + 1)
            checksum = response.headers.get('X-Content-SHA256')
        if len(content) > 5 * 1024 * 1024 or mime not in ('image/png', 'image/jpeg'):
            raise ValueError('Invalid image type or size')
        if not (content.startswith(b'\x89PNG\r\n\x1a\n') if mime == 'image/png' else content.startswith(b'\xff\xd8\xff')):
            raise ValueError('Image header mismatch')
        actual = hashlib.sha256(content).hexdigest()
        if not checksum or actual != checksum:
            raise ValueError('Image checksum mismatch')
        directory = Path(directory) if directory else Path(os.environ['LOCALAPPDATA']) / 'RemoteBHubA' / 'artifacts'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (artifact_id + ('.png' if mime == 'image/png' else '.jpg'))
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(content)
        temporary.replace(path)
        return {'downloaded': str(path.resolve()), 'content_type': mime, 'bytes': len(content),
                'sha256': actual, 'image_requires_explicit_open': True}
