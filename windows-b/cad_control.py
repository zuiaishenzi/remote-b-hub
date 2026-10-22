"""Serialized remote startup and pause recovery. Never kills SW or a live caller."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

from cad_control_schema import validate_cad_control
from sw_script import LOCK
from windows_processes import process_family


def cad_state(directory):
    path = Path(directory) / LOCK
    value = {'paused': path.exists(), 'pause_id': None, 'helper_pid': None,
             'helper_running': None, 'can_resume': False}
    if not path.exists():
        return value
    raw = path.read_bytes()
    value['pause_id'] = hashlib.sha256(raw).hexdigest()
    try:
        record = json.loads(raw)
        pid = record.get('pid')
        if type(pid) is not int or pid <= 0:
            raise ValueError('Pause record has no valid caller PID; local inspection is required')
        value['helper_pid'] = pid
        value['audit_id'] = Path(record.get('audit', '')).name
        value['script_sha256'] = record.get('script_sha256')
        # SW is expected to outlive a startup helper; never treat it as a caller
        # to kill/wait for. Onefile bootloader children must still block unlock.
        value['helper_process_pids'] = process_family(pid, exclude_names={'sldworks.exe'})
        value['helper_running'] = bool(value['helper_process_pids'])
        value['can_resume'] = not value['helper_running']
        value['reason'] = ('Previous caller is still running; wait, do not retry or force unlock'
                           if value['helper_running'] else 'Caller exited; inspect SW and acknowledge the current pause')
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        value['reason'] = str(exc)[:400]
    return value


def resume_cad(params, config, directory, progress):
    validate_cad_control(params)
    if not config.get('allow_sw_scripts'):
        raise PermissionError('B must enable trusted A script control before remote recovery')
    directory = Path(directory)
    state = cad_state(directory)
    if not state['paused']:
        raise RuntimeError('CAD is not paused; no recovery was performed')
    if params['pause_id'] != state['pause_id']:
        raise RuntimeError('Pause changed; inspect the latest CAD state before recovery')
    if not state['can_resume']:
        raise RuntimeError('Recovery refused: ' + state.get('reason', 'Caller state unknown'))
    lock = directory / LOCK
    raw = lock.read_bytes()
    if hashlib.sha256(raw).hexdigest() != params['pause_id']:
        raise RuntimeError('Pause changed during recovery; no unlock performed')
    # The singleton worker serializes this job with every other CAD/control job.
    audit = directory / 'script-runs' / ('recovery-' + uuid.uuid4().hex)
    audit.mkdir(parents=True)
    (audit / 'recovery.json').write_text(json.dumps({'actor': 'authenticated-A',
        'acknowledged': True, 'pause_id': params['pause_id'], 'previous_pid': state['helper_pid'],
        'created': time.time()}), encoding='utf-8')
    lock.replace(audit / 'previous-pause.json')
    progress('cad_resumed', 'A 已确认当前暂停状态；旧脚本进程已退出，已解除暂停。下一步先只读检查 SW。')
    return {'resumed': True, 'previous_pause_id': params['pause_id'], 'audit_id': audit.name,
            'paused': False, 'next_step': 'Read SW session before any edit; do not repeat the timed-out script'}


def start_helper(folder):
    """Separate-process entry: potentially blocking COM must not block the worker."""
    from desktop_worker import ensure_solidworks, write_json
    folder = Path(folder)
    config = json.loads((folder / 'start-config.json').read_text(encoding='utf-8'))
    # The parent holds the global gate; this child owns this separate audit folder.
    config['_directory'] = str(folder)
    config['auto_start_sw'] = True
    try:
        result = ensure_solidworks(config, lambda stage, detail: write_json(
            folder / 'progress.json', {'stage': stage, 'detail': detail}))
        answer = {'ok': True, 'value': result}
    except BaseException:
        answer = {'ok': False, 'traceback': traceback.format_exc()[-6500:]}
    write_json(folder / 'response.json', answer)
    return 0


def start_solidworks(config, directory, progress, stop_requested=lambda: False):
    from desktop_worker import write_json
    directory = Path(directory)
    if (directory / LOCK).exists():
        raise RuntimeError('CAD is paused; inspect/recover it before requesting SW startup')
    if stop_requested():
        raise RuntimeError('Agent is stopping; no SW start request was sent')
    folder = directory / 'script-runs' / ('start-' + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    timeout = max(10, min(300, int(config.get('sw_start_timeout', 180))))
    write_json(folder / 'start-config.json', {'sw_exe': config['sw_exe'], 'sw_start_timeout': timeout})
    lock = directory / LOCK
    write_json(lock, {'audit': str(folder), 'operation': 'start_solidworks'})
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command.append(str(Path(__file__).with_name('desktop_launcher.py')))
    command += ['--start-sw-helper', str(folder)]
    env = {k: v for k, v in os.environ.items() if k not in
           ('REMOTE_B_AGENT_TOKEN', 'REMOTE_B_CLIENT_TOKEN', 'HUB_A_TOKEN', 'HUB_B_TOKEN')}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    try:
        child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        lock.unlink()
        raise
    write_json(lock, {'pid': child.pid, 'audit': str(folder), 'operation': 'start_solidworks'})
    progress('remote_start_sw', 'A 已请求启动 SW；独立进程检查本会话实例与 COM，不关闭文档')
    deadline, previous = time.monotonic() + timeout + 20, None
    while child.poll() is None:
        if time.monotonic() >= deadline or stop_requested():
            raise RuntimeError('SW startup caller still running; CAD paused. Inspect CAD state; no process was killed')
        file = folder / 'progress.json'
        if file.exists():
            item = json.loads(file.read_text(encoding='utf-8'))
            if item != previous:
                progress(item['stage'], item['detail'])
                previous = item
        time.sleep(.25)
    response = folder / 'response.json'
    if child.returncode or not response.is_file():
        raise RuntimeError('SW startup caller returned no result; CAD remains paused')
    answer = json.loads(response.read_text(encoding='utf-8'))
    if type(answer.get('ok')) is not bool:
        raise RuntimeError('Invalid startup response; CAD remains paused')
    lock.unlink()
    if not answer['ok']:
        raise RuntimeError('SW startup failed:\n' + answer.get('traceback', 'No traceback'))
    return {**answer['value'], 'audit_id': folder.name, 'documents_closed': False}


def execute_control(params, config, directory, progress, stop_requested=lambda: False):
    validate_cad_control(params)
    if params['action'] == 'state':
        return cad_state(directory)
    if params['action'] == 'resume':
        return resume_cad(params, config, directory, progress)
    return start_solidworks(config, directory, progress, stop_requested)
