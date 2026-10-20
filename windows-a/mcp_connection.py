"""Resolve A credentials without depending on a launcher process environment."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from desktop_config import unprotect_token


def load_connection(environ=None):
    env = os.environ if environ is None else environ
    server, token = env.get('REMOTE_B_API_URL'), env.get('REMOTE_B_CLIENT_TOKEN')
    if server or token:
        if not server or not token:
            raise RuntimeError('Set both REMOTE_B_API_URL and REMOTE_B_CLIENT_TOKEN; partial overrides are refused')
    else:
        local = env.get('LOCALAPPDATA')
        if not local:
            raise RuntimeError('LOCALAPPDATA is missing; save A client configuration or set both connection variables')
        path = Path(local) / 'RemoteBHubA' / 'config.json'
        if not path.is_file():
            raise RuntimeError('No A connection configured; open RemoteBClient.exe and save NAS address and A Token')
        try:
            if path.stat().st_size > 65536:
                raise ValueError('oversized configuration')
            profile = json.loads(path.read_text(encoding='utf-8-sig'))
            server = profile['server_url']
            token = unprotect_token(profile['token_dpapi'])
        except Exception:
            raise RuntimeError('Cannot read A client configuration for this Windows user; reopen A client and save it again') from None
    if type(server) is not str or type(token) is not str:
        raise RuntimeError('Invalid A connection configuration')
    server = server.rstrip('/')
    url = urlsplit(server)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise RuntimeError('Invalid NAS service URL')
    if len(token) < 32 or any(c.isspace() for c in token):
        raise RuntimeError('Invalid A Token; save it again in the A client')
    return server, token
