# SPDX-License-Identifier: AGPL-3.0-or-later
"""Runs INSIDE Blender. Loopback, authenticated, main-thread bpy dispatch.

No relay credentials. RFingAdam handlers are loaded only inside Blender;
its unauthenticated socket server is never started. See third_party/rfingadam.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import time
import traceback

PROTOCOL = 1
MAX_PACKET = 45000
MAX_RESPONSE = 36000  # ASCII-escaped JSON budget leaves room for relay diagnostics.


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    for attempt in range(81):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 80:
                raise
            time.sleep(.025)


class BoundedLog(io.TextIOBase):
    def __init__(self):
        self.text = ''

    def write(self, value):
        self.text = (self.text + str(value))[-6000:]
        return len(value)

    def flush(self):
        pass


def snapshot():
    import bpy
    scene = bpy.context.scene
    objects = list(scene.objects)
    return {'blender_version': bpy.app.version_string, 'pid': os.getpid(),
            'file': bpy.data.filepath, 'modified': bpy.data.is_dirty,
            'scene': scene.name, 'unit_system': scene.unit_settings.system,
            'scale_length': scene.unit_settings.scale_length,
            'frame': scene.frame_current, 'object_count': len(objects),
            'objects': [{'name': o.name, 'type': o.type,
                         'location': list(o.location), 'dimensions': list(o.dimensions),
                         'modifiers': [m.type for m in o.modifiers][:20]}
                        for o in objects[:80]], 'truncated': len(objects) > 80}


class Bridge:
    def __init__(self, settings):
        self.settings = settings
        self.directory = Path(settings['directory'])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.listener = None
        self.clients = {}
        self.handlers = None
        self.session_id = secrets.token_hex(16)
        self.token = settings['token']
        if len(self.token) < 32:
            raise ValueError('Invalid local bridge secret')

    def start(self):
        import bpy
        listener = socket.socket()
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(('127.0.0.1', self.settings['port']))
            listener.listen(4)
            listener.setblocking(False)
        except Exception:
            listener.close()
            raise
        self.listener = listener
        bpy.app.timers.register(self.tick, first_interval=.1, persistent=True)

    def stop(self):
        import bpy
        if bpy.app.timers.is_registered(self.tick):
            bpy.app.timers.unregister(self.tick)
        for client in list(self.clients):
            client.close()
        self.clients.clear()
        if self.listener:
            self.listener.close()
            self.listener = None

    def tick(self):
        if not self.listener:
            return None
        try:
            # Bound per-tick work. bpy is never accessed from a socket thread.
            for _ in range(4):
                try:
                    client, _ = self.listener.accept()
                except BlockingIOError:
                    break
                client.setblocking(False)
                if len(self.clients) >= 4:
                    client.close()
                else:
                    self.clients[client] = [bytearray(), bytearray(), time.monotonic()]
            for client, state in list(self.clients.items()):
                incoming, outgoing, created = state
                try:
                    if outgoing:
                        count = client.send(outgoing)
                        del outgoing[:count]
                        if not outgoing:
                            self.drop(client)
                        continue
                    if time.monotonic() - created > 5:
                        self.drop(client)
                        continue
                    data = client.recv(8192)
                    if not data:
                        self.drop(client)
                        continue
                    incoming.extend(data)
                    if len(incoming) > MAX_PACKET:
                        self.drop(client)
                        continue
                    if b'\n' not in incoming:
                        continue
                    response = self.handle(bytes(incoming).split(b'\n', 1)[0])
                    outgoing.extend(json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n')
                except BlockingIOError:
                    pass
                except (ConnectionError, OSError):
                    self.drop(client)
        except Exception:
            traceback.print_exc()
        return .05

    def drop(self, client):
        self.clients.pop(client, None)
        client.close()

    def handle(self, packet):
        identity = None
        audit = None
        started = False
        report = {}
        output = BoundedLog()
        try:
            request = json.loads(packet)
            if type(request) is not dict or type(request.get('token')) is not str or not secrets.compare_digest(request['token'], self.token):
                return {'ok': False, 'error': 'Unauthorized local Blender bridge'}
            import re
            identity = request.get('id')
            if type(identity) is not str or not re.fullmatch('[a-f0-9]{32}', identity):
                raise ValueError('Invalid request identity')
            params = request['params']
            from blender_schema import validate_blender_request
            validate_blender_request(params)
            digest = hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            candidate = self.directory / 'blender-runs' / identity
            candidate.mkdir(parents=True, exist_ok=True)
            receipt = candidate / 'response.json'
            if receipt.exists():
                previous = json.loads(receipt.read_text(encoding='utf-8'))
                if previous.get('request_sha256') != digest:
                    raise ValueError('Request identity already used for different parameters')
                return previous  # Receipt replay never re-executes a command.
            if (candidate / 'state.json').exists():
                raise RuntimeError('This request was already started; inspect its audit, do not retry')
            audit = candidate
            atomic_json(audit / 'request.json', {'params': params, 'sha256': digest})
            atomic_json(audit / 'state.json', {'stage': 'running', 'pid': os.getpid(), 'started': time.time()})
            started = True
            report = {'id': identity, 'request_sha256': digest, 'session_id': self.session_id}
            action = params['action']
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                report['before'] = snapshot()
                if action in ('status', 'inspect'):
                    value = snapshot()
                elif action == 'script':
                    import bpy
                    namespace = {'bpy': bpy, '__builtins__': __builtins__, 'snapshot': snapshot,
                                 'output_dir': self.settings['output_dir'], 'log': print}
                    exec(compile(params['code'], '<remote-blender-script>', 'exec'), namespace)
                    value = namespace.get('result', {})
                    if type(value) is not dict:
                        raise ValueError('Script result must be a JSON object')
                elif action == 'tool':
                    if self.handlers is None:
                        from blender_mcp_addon.handlers import CommandHandlers
                        self.handlers = CommandHandlers()
                    value = self.handlers.handle(params['name'], params.get('arguments', {}))
                    if isinstance(value, dict) and (value.get('success') is False or value.get('error')):
                        raise RuntimeError('Upstream Blender handler failed: ' + str(value))
                else:
                    raise ValueError('Action is not a Blender main-thread command')
                report.update(ok=True, value=value, after=snapshot())
                json.dumps(report, allow_nan=False)  # No implicit repr of bpy objects.
        except Exception as exc:
            report.update(ok=False, error=f'{type(exc).__name__}: {exc}'[:1200],
                          traceback=traceback.format_exc()[-6000:])
            report.pop('value', None)
            if started:
                try:
                    report['after'] = snapshot()
                except Exception:
                    pass
        report['log_tail'] = output.text
        if len(json.dumps(report, allow_nan=False).encode('utf-8')) > MAX_RESPONSE:
            report = {'ok': False, 'id': identity, 'error': 'Response exceeds relay budget; command may have changed the scene. Use a smaller result.',
                      'request_sha256': report.get('request_sha256'), 'log_tail': output.text}
        if audit is not None and started:
            atomic_json(audit / 'response.json', report)
            atomic_json(audit / 'state.json', {'stage': 'done' if report['ok'] else 'error', 'pid': os.getpid(), 'finished': time.time()})
        return report


_bridge = None


def register(settings_path=None):
    global _bridge
    if _bridge:
        return
    settings_file = Path(settings_path) if settings_path else Path(os.environ['LOCALAPPDATA']) / 'RemoteBHub' / 'blender-bridge.json'
    settings = json.loads(settings_file.read_text(encoding='utf-8'))
    bridge = Bridge(settings)
    bridge.start()
    _bridge = bridge


def unregister():
    global _bridge
    if _bridge:
        _bridge.stop()
        _bridge = None


if __name__ == '__main__':
    # Bootstrap generated by the B controller imports this module, then starts it.
    register()
