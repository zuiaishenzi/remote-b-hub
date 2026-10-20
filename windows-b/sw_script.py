"""Full-trust Python COM execution. Process separation is NOT a security sandbox."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

from script_schema import validate_script_request

LOCK = 'cad-state-unknown.json'


class ScriptExecutionError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('SW script failed; do not repeat unchanged.\n' + report.get('traceback', 'No traceback'))


class BoundedLog(io.TextIOBase):
    def __init__(self):
        self.text = ''
        self.truncated = False

    def write(self, text):
        self.text += str(text)
        if len(self.text) > 6000:
            self.text = self.text[-6000:]
            self.truncated = True
        return len(text)

    def flush(self):
        pass


def snapshot(sw):
    """Read active document identity and a bounded feature list. No rebuild/save."""
    from solidworks_box import com_read
    value = {'connected': True, 'revision': str(com_read(sw, 'RevisionNumber'))}
    model = com_read(sw, 'ActiveDoc')
    if model is None:
        value['document'] = None
        return value
    document = {'title': str(com_read(model, 'GetTitle')),
                'path': str(com_read(model, 'GetPathName')),
                'type': int(com_read(model, 'GetType')),
                'modified': bool(com_read(model, 'GetSaveFlag'))}
    features = []
    feature = com_read(model, 'FirstFeature')
    while feature is not None and len(features) < 120:
        features.append({'name': str(com_read(feature, 'Name'))[:160],
                         'type': str(com_read(feature, 'GetTypeName2'))[:100]})
        feature = com_read(feature, 'GetNextFeature')
    document.update(features=features, features_truncated=feature is not None)
    value['document'] = document
    return value


def run_payload(folder, connector=None):
    """Child entry point; a connector may be injected by contract tests only."""
    folder = Path(folder)
    params = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    digest = validate_script_request(params)
    log = BoundedLog()
    answer = {'ok': False, 'script_sha256': digest}
    pythoncom = None
    started = time.monotonic()
    try:
        if connector is None:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            connector = lambda: win32com.client.GetActiveObject('SldWorks.Application')
        with redirect_stdout(log), redirect_stderr(log):
            sw = connector()
            answer['before'] = snapshot(sw)
            if params['mode'] == 'execute':
                from solidworks_box import com_read
                context = json.loads((folder / 'context.json').read_text(encoding='utf-8'))
                namespace = {'__name__': '__remote_sw_script__', 'sw': sw,
                             'model': com_read(sw, 'ActiveDoc'), 'read': com_read,
                             'snapshot': lambda: snapshot(sw), 'log': print,
                             'output_dir': context['output_dir'],
                             'part_template': context['part_template'],
                             'assembly_template': context['assembly_template'], 'result': {}}
                exec(compile(params['code'], '<remote-sw-script>', 'exec'), namespace)
                result = namespace['result']
                if type(result) is not dict:
                    raise ValueError('Script must assign a JSON object to result')
                # Fail on NaN, COM objects and oversized results, never fabricate success.
                if len(json.dumps(result, ensure_ascii=False, allow_nan=False)) > 16000:
                    raise ValueError('Script result exceeds 16000 characters')
                answer['result'] = result
            answer['after'] = snapshot(sw)
            answer['ok'] = True
    except BaseException:
        answer['traceback'] = traceback.format_exc()[-6500:]
    finally:
        if pythoncom is not None:
            pythoncom.CoUninitialize()
    answer.update(log=log.text, log_truncated=log.truncated,
                  elapsed_seconds=round(time.monotonic() - started, 3),
                  engineering_validation='Not inferred; validate geometry, constraints and save explicitly')
    try:
        encoded = json.dumps(answer, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 46000:
            raise ValueError('Snapshot/output exceeds relay budget')
    except (ValueError, TypeError):
        encoded = json.dumps({'ok': False, 'script_sha256': digest,
                              'traceback': traceback.format_exc()[-6500:]})
    (folder / 'response.tmp').write_text(encoded, encoding='utf-8')
    (folder / 'response.tmp').replace(folder / 'response.json')
    return 0


def execute_script(params, config, directory, progress):
    digest = validate_script_request(params)
    if params['mode'] == 'execute' and not config.get('allow_sw_scripts', False):
        raise PermissionError('B 未启用“允许 A 执行完整权限 SW Python 脚本”；请求未执行')
    directory = Path(directory)
    if (directory / LOCK).exists():
        raise RuntimeError('CAD paused; local acknowledgement required')
    folder = directory / 'script-runs' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    (folder / 'request.json').write_text(json.dumps(params, ensure_ascii=False), encoding='utf-8')
    context = {k: config.get(k, '') for k in ('output_dir', 'part_template', 'assembly_template')}
    (folder / 'context.json').write_text(json.dumps(context), encoding='utf-8')
    progress('script_start', f"mode={params['mode']} SHA256={digest}; audit={folder.name}")
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command.append(str(Path(__file__).with_name('desktop_launcher.py')))
    command += ['--run-sw-script', str(folder)]
    env = {k: v for k, v in os.environ.items() if k not in
           ('REMOTE_B_AGENT_TOKEN', 'REMOTE_B_CLIENT_TOKEN', 'HUB_A_TOKEN', 'HUB_B_TOKEN')}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    # Reserve before spawning, so worker crashes/restarts cannot run another CAD job.
    lock = directory / LOCK
    lock.write_text(json.dumps({'audit': str(folder), 'script_sha256': digest}), encoding='utf-8')
    try:
        child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        lock.unlink()
        raise
    lock.write_text(json.dumps({'pid': child.pid, 'audit': str(folder), 'script_sha256': digest}), encoding='utf-8')
    try:
        child.wait(timeout=params.get('timeout_seconds', 60))
    except subprocess.TimeoutExpired:
        # Leave the child/SW alive: killing a caller does not cancel a COM call.
        (directory / LOCK).write_text(json.dumps({'pid': child.pid, 'audit': str(folder),
                                                 'script_sha256': digest}), encoding='utf-8')
        raise RuntimeError('SW script timed out; child/SW may still be running. CAD paused. '
                           'Do not retry. Inspect B, stop agent, then locally acknowledge state.')
    response = folder / 'response.json'
    if child.returncode or not response.is_file():
        (directory / LOCK).write_text(json.dumps({'pid': child.pid, 'audit': str(folder)}), encoding='utf-8')
        raise RuntimeError('Script helper exited without a result; CAD state unknown, local acknowledgement required')
    from desktop_config import redact
    answer = json.loads(redact(response.read_text(encoding='utf-8'), config.get('token', '')))
    # Scrub local response too; no credentials are passed intentionally to scripts.
    response.write_text(json.dumps(answer, ensure_ascii=False), encoding='utf-8')
    if answer.get('script_sha256') != digest:
        raise RuntimeError('Script response hash mismatch; CAD paused')
    lock.unlink()
    if answer.get('log'):
        progress('script_log', answer['log'][-1200:])
    if not answer.get('ok'):
        raise ScriptExecutionError(answer)
    answer['audit_id'] = folder.name
    return answer
