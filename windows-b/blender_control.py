"""B-side Blender lifecycle and audited loopback transport, independent of SW."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
import zipfile

from blender_schema import validate_blender_request

LOCK = 'blender-state-unknown.json'
UPSTREAM_COMMIT = 'efbafb6a9e019a03a5887ff943462715e0f386dc'


class BlenderError(RuntimeError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report or {}


def assets():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'third_party' / 'rfingadam'


def catalog(name=None):
    path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'blender-tools.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    if name:
        entries = [t for t in document['tools'] if t['name'] == name]
        if not entries:
            raise ValueError('Unknown upstream Blender command')
        return {**document, 'tools': entries, 'validation': 'Catalog presence is not runtime acceptance'}
    return {'upstream': document['upstream'], 'commit': document['commit'], 'count': len(document['tools']),
            'tools': [{'name': t['name'], 'description': t['description'][:220]} for t in document['tools']],
            'usage': 'Query a name for its full input schema, then call computer_b_blender_command. All tools require B opt-in.',
            'validation': 'Not all upstream commands are tested; AI backends need separate configuration.'}


def discover_executable(config):
    configured = str(config.get('blender_exe', '')).strip()
    if configured:
        path = Path(configured)
        return path if path.is_file() and path.name.lower() == 'blender.exe' else None
    candidates = []
    for root in (Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Blender Foundation',
                 Path(os.environ.get('LOCALAPPDATA', '.')) / 'Programs' / 'Blender Foundation'):
        if root.is_dir():
            candidates.extend(root.glob('Blender */blender.exe'))
    located = shutil.which('blender.exe')
    if located:
        candidates.append(Path(located))
    return sorted(candidates, key=lambda p: str(p), reverse=True)[0] if candidates else None


def prepare_bridge(config, directory):
    """Stage immutable sources for Blender; no plugin install or preference changes."""
    from blender_bridge import atomic_json
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    settings_path = directory / 'blender-bridge.json'
    old = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
    settings = {'directory': str(directory.resolve()), 'port': config.get('blender_port', 18766),
                'token': old.get('token') or secrets.token_hex(32),
                'output_dir': str(Path(config.get('blender_output_dir') or config['output_dir']).resolve())}
    Path(settings['output_dir']).mkdir(parents=True, exist_ok=True)
    atomic_json(settings_path, settings)
    stage = directory / 'blender-bridge' / UPSTREAM_COMMIT
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copytree(assets(), stage / 'rfingadam', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    source = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    for name in ('blender_bridge.py', 'blender_schema.py'):
        # PyInstaller must bundle these as ordinary data for Blender's interpreter.
        shutil.copyfile(source / name, stage / name)
    bootstrap = stage / 'bootstrap.py'
    bootstrap.write_text('import sys,json\nfrom pathlib import Path\n'
        + 'sys.path[:0]=' + repr([str(stage), str(stage / 'rfingadam')]) + '\n'
        + 'from blender_bridge import Bridge\n'
        + '_remoteb_bridge=Bridge(json.loads(Path(' + repr(str(settings_path)) + ').read_text(encoding="utf-8")))\n'
        + '_remoteb_bridge.start()\n', encoding='utf-8')
    return settings, bootstrap


def export_addon(config, directory, destination):
    """For an already running Blender: install this ZIP once through Preferences."""
    settings, bootstrap = prepare_bridge(config, directory)
    stage = bootstrap.parent
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        prefix = 'remote_b_blender/'
        init = ('bl_info={"name":"Remote B Hub Blender Bridge","author":"Remote B Hub",'
                '"version":(1,0,0),"blender":(4,2,0),"category":"Interface"}\n'
                'import sys\nfrom pathlib import Path\n'
                'sys.path[:0]=[str(Path(__file__).parent),str(Path(__file__).parent/"rfingadam")]\n'
                'from blender_bridge import register as _register,unregister\n'
                'def register():\n    _register(' + repr(str(Path(directory).resolve() / 'blender-bridge.json')) + ')\n')
        archive.writestr(prefix + '__init__.py', init)
        for name in ('blender_bridge.py', 'blender_schema.py'):
            archive.write(stage / name, prefix + name)
        for path in (stage / 'rfingadam').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                archive.write(path, prefix + 'rfingadam/' + path.relative_to(stage / 'rfingadam').as_posix())
    return {'addon': str(destination), 'bytes': Path(destination).stat().st_size,
            'instructions': 'Blender: Edit > Preferences > Add-ons > Install from Disk, select ZIP and enable Remote B Hub Blender Bridge. No public port needed.'}


def settings_for(directory):
    path = Path(directory) / 'blender-bridge.json'
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def exchange(settings, params, identity, timeout):
    packet = json.dumps({'token': settings['token'], 'id': identity, 'params': params}, ensure_ascii=False).encode('utf-8') + b'\n'
    deadline = time.monotonic() + timeout
    with socket.create_connection(('127.0.0.1', settings['port']), timeout=min(3, timeout)) as client:
        client.settimeout(max(.01, deadline - time.monotonic()))
        client.sendall(packet)
        data = bytearray()
        while b'\n' not in data:
            client.settimeout(max(.01, deadline - time.monotonic()))
            chunk = client.recv(8192)
            if not chunk:
                raise ConnectionError('Blender closed the connection before returning a complete receipt')
            data.extend(chunk)
            if len(data) > 50000:
                raise ValueError('Blender response exceeds transport limit')
        response = json.loads(bytes(data).split(b'\n', 1)[0])
    if response.get('id') != identity:
        raise ValueError('Blender response identity mismatch; command state is uncertain')
    return response


def blender_state(directory):
    path = Path(directory) / LOCK
    if not path.exists():
        return {'paused': False, 'can_resume': False}
    raw = path.read_bytes()
    lock = json.loads(raw)
    identity = lock['request_id']
    receipt = Path(directory) / 'blender-runs' / identity / 'response.json'
    response = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
    return {'paused': True, 'pause_id': hashlib.sha256(raw).hexdigest(),
            'request_id': identity, 'reason': lock['reason'], 'created': lock['created'],
            'can_resume': bool(response and response.get('id') == identity),
            'late_result': response, 'audit': str(receipt.parent)}


def execute_blender(params, config, directory, progress=lambda *_: None, job_id=None):
    from blender_bridge import atomic_json
    validate_blender_request(params)
    directory = Path(directory)
    action = params['action']
    if action == 'state':
        return blender_state(directory)
    if action == 'resume':
        if not config.get('allow_blender_control'):
            raise PermissionError('B has not enabled full-trust Blender remote control')
        state = blender_state(directory)
        if not state.get('paused') or state['pause_id'] != params['pause_id'] or not state['can_resume']:
            raise RuntimeError('Blender pause changed or old command has no terminal receipt; inspect B, do not force unlock')
        target = directory / 'blender-runs' / state['request_id'] / ('recovery-' + uuid.uuid4().hex + '.json')
        atomic_json(target, {'actor': 'authenticated-A', 'pause_id': state['pause_id'], 'acknowledged': True, 'time': time.time()})
        (directory / LOCK).unlink()
        return {'resumed': True, 'audit': str(target), 'previous_result': state['late_result']}
    if action == 'image':
        if not config.get('blender_images_enabled'):
            raise PermissionError('B has not enabled Blender image upload')
        if not job_id:
            raise ValueError('Image upload requires a real job')
        from screen_capture import upload_image
        from PIL import Image
        import io
        root = Path(config.get('blender_output_dir') or config['output_dir']).resolve()
        path = (root / params['file']).resolve()
        if path.parent != root or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('Image must exist inside configured Blender output root and be at most 10MiB')
        with Image.open(path) as picture:
            if picture.width * picture.height > 20_000_000:
                raise ValueError('Image dimensions too large')
            picture = picture.convert('RGB')
            picture.thumbnail((1920, 1440))
            output = io.BytesIO()
            picture.save(output, format='JPEG', quality=85)
        return {'artifacts': [upload_image(job_id, config, output.getvalue(), 'image/jpeg')], 'source': str(path)}
    state = blender_state(directory)
    if state.get('paused'):
        raise BlenderError('Blender is paused; inspect state/late result before resuming', state)
    if action in ('tool', 'script') and not config.get('allow_blender_control'):
        raise PermissionError('B has not enabled full-trust Blender remote control; nothing executed')
    if action == 'tool':
        catalog(params['name'])
    settings = settings_for(directory)
    if settings:
        try:
            report = exchange(settings, {'action': 'status'}, uuid.uuid4().hex, 3)
            if not report.get('ok'):
                raise BlenderError('Blender bridge rejected status', report)
        except Exception as exc:
            report = None
            status_error = str(exc)
    else:
        report = None
        status_error = 'Bridge has not been prepared'
    if not report:
        if action == 'status':
            executable = discover_executable(config)
            return {'connected': False, 'executable': str(executable) if executable else None,
                    'bridge_error': status_error, 'paused': False}
        if action != 'start' and not config.get('auto_start_blender', True):
            raise RuntimeError('Blender is not connected and auto-start is disabled')
        from windows_processes import process_session, processes_in_session
        processes = processes_in_session('blender.exe', process_session())
        if processes:
            raise RuntimeError('Blender is already running but its bridge is unavailable. Enable the exported Remote B Hub add-on; no second instance was started. PIDs=' + str(processes))
        executable = discover_executable(config)
        if not executable:
            raise FileNotFoundError('Blender not found; configure blender.exe in B Settings (Blender 4.2+ recommended)')
        settings, bootstrap = prepare_bridge(config, directory)
        progress('starting_blender', '启动 Blender 并加载本地鉴权桥接')
        env = {key: value for key, value in os.environ.items() if not key.startswith(('REMOTE_B_', '_PYI_'))}
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        with (directory / 'blender-start.log').open('ab') as stream:
            process = subprocess.Popen([str(executable), '--python', str(bootstrap)], cwd=str(executable.parent),
                                       env=env, stdout=stream, stderr=stream)
        progress('waiting_blender', '等待 Blender 主线程桥接 PID=' + str(process.pid))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                report = exchange(settings, {'action': 'status'}, uuid.uuid4().hex, 2)
                if report.get('ok'):
                    break
            except (OSError, ValueError):
                pass
            if process.poll() is not None:
                raise RuntimeError('Blender exited during startup; inspect blender-start.log')
            time.sleep(.5)
        else:
            raise TimeoutError('Blender bridge startup timed out; process left open. Check Blender, do not start a duplicate instance.')
    if action in ('status', 'start'):
        return {'connected': True, 'session': report['value'], 'upstream_commit': UPSTREAM_COMMIT}
    identity = uuid.uuid4().hex
    timeout = params.get('timeout_seconds', 60)
    audit = directory / 'blender-runs' / identity
    audit.mkdir(parents=True, exist_ok=True)
    atomic_json(audit / 'submitted.json', {'params': params, 'job_id': job_id, 'created': time.time()})
    progress('blender_execute', f"action={action}; audit={identity}; timeout={timeout}s")
    # Reserve pause before transmission. A crash/disconnect cannot silently unlock.
    atomic_json(directory / LOCK, {'request_id': identity, 'created': time.time(), 'reason': 'Blender command in flight; completion not confirmed'})
    try:
        report = exchange(settings, params, identity, timeout)
    except Exception as exc:
        raise BlenderError('Blender command has no confirmed result; Blender paused. Do not retry. Read state and inspect B. ' + str(exc), blender_state(directory)) from exc
    atomic_json(audit / 'response.json', report)
    (directory / LOCK).unlink()
    if not report.get('ok'):
        raise BlenderError('Blender execution failed; scene may be partially changed: ' + report.get('error', ''), report)
    return report
