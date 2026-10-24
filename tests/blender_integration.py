"""Real portable Blender acceptance, isolated factory scene, no user's model/profile.

Usage: python tests/blender_integration.py path/to/blender.exe [RemoteBHub.exe]
Exercises the same NAS HTTP contract and, optionally, the frozen Windows worker.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'windows-b'), str(ROOT/'linux-server')]
from blender_control import prepare_bridge, execute_blender, exchange
from desktop_config import DEFAULTS, save_config
import urllib.request


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    executable = Path(sys.argv[1]).resolve()
    frozen = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    # Keep results as actual build artifacts for review, never fabricated runtime data.
    directory = ROOT/'build'/('blender-acceptance-' + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    config = {**DEFAULTS, 'blender_exe': str(executable), 'output_dir': str(directory/'output'),
              'blender_output_dir': str(directory/'output'), 'blender_port': unused_port(),
              'allow_blender_control': True, 'blender_images_enabled': True, 'auto_start_agent': False,
              'server_url': 'http://127.0.0.1:' + str(unused_port()), 'token': 'b'*64}
    settings, bootstrap = prepare_bridge(config, directory)
    runner = directory/'factory-runner.py'
    runner.write_text(bootstrap.read_text(encoding='utf-8') + '\nimport time\n'
        + 'deadline=time.monotonic()+240\n'
        + 'while time.monotonic()<deadline and not Path(' + repr(str(directory/'test-finished')) + ').exists():\n'
        + '    _remoteb_bridge.tick()\n    time.sleep(.01)\n'
        + '_remoteb_bridge.stop()\n', encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('REMOTE_B_', '_PYI_'))}
    log = (directory/'blender.log').open('wb')
    process = subprocess.Popen([str(executable), '--background', '--factory-startup', '--disable-autoexec', '--python', str(runner)],
                               env=env, stdout=log, stderr=log)
    worker = None
    server = None
    results = {'real_blender': True, 'mode': 'frozen-worker' if frozen else 'source-worker', 'jobs': []}
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                ready = exchange(settings, {'action': 'status'}, uuid.uuid4().hex, 2)
                assert ready['ok'], ready
                results['version'] = ready['value']['blender_version']
                break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('Actual Blender did not start; inspect ' + str(directory/'blender.log'))
        os.environ.update(HUB_A_TOKEN='a'*64, HUB_B_TOKEN='b'*64, HUB_DB=str(directory/'relay.sqlite3'))
        import server as hub
        from fastapi.testclient import TestClient
        client = TestClient(hub.app)
        ah = {'Authorization': 'Bearer ' + 'a'*64}
        bh = {'Authorization': 'Bearer ' + 'b'*64}
        if True:
            import uvicorn
            from urllib.parse import urlsplit
            server = uvicorn.Server(uvicorn.Config(hub.app, host='127.0.0.1', port=urlsplit(config['server_url']).port, log_level='error'))
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            deadline = time.monotonic()+10
            while not server.started and time.monotonic()<deadline:
                time.sleep(.05)
            assert server.started
        if frozen:
            save_config(directory, config)
            worker = subprocess.Popen([str(frozen), '--worker', '--data-dir', str(directory)],
                         env={**env, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

        def submit(params, expect_error=False):
            posted = client.post('/api/jobs', headers=ah, json={'operation': 'blender_control', 'params': params})
            assert posted.status_code == 200, posted.text
            identity = posted.json()['job_id']
            if not frozen:
                claimed = client.get('/agent/next', headers=bh).json()['job']
                assert claimed['job_id'] == identity
                try:
                    value = execute_blender(params, config, directory, job_id=identity)
                    answer = {'ok': True, 'value': value}
                except Exception as exc:
                    answer = {'ok': False, 'error': str(exc), 'diagnostics': getattr(exc, 'report', {})}
                delivered = client.post('/agent/jobs/'+identity+'/result', headers=bh, json=answer)
                assert delivered.status_code == 200, delivered.text
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                job = client.get('/api/jobs/'+identity, headers=ah).json()
                if job['status'] in ('done', 'error'):
                    break
                time.sleep(.1)
            else:
                raise AssertionError('Job did not finish: ' + identity)
            results['jobs'].append(job)
            assert job['status'] == ('error' if expect_error else 'done'), job
            return job['result'].get('value', {})

        assert 'blender_control' in client.get('/health').json()['capabilities']
        rejected = client.post('/api/jobs', headers=ah, json={'operation': 'blender_control', 'params': {'action': 'script', 'code': 'if'}})
        assert rejected.status_code == 400
        status = submit({'action': 'status'})
        assert status['connected']
        reused = submit({'action': 'start'})
        assert reused['session']['pid'] == status['session']['pid'] == process.pid
        initial = submit({'action': 'inspect'})
        assert initial['value']['object_count'] == 3
        created = submit({'action': 'tool', 'name': 'object_create', 'arguments': {'type': 'cube', 'name': 'RemoteB_Acceptance_Cube', 'location': [3, 0, 0]}})
        assert created['after']['object_count'] == 4
        submit({'action': 'tool', 'name': 'material_create', 'arguments': {'name': 'RemoteB_Acceptance_Material'}})
        submit({'action': 'tool', 'name': 'modifier_add', 'arguments': {'object_name': 'RemoteB_Acceptance_Cube', 'modifier_type': 'BEVEL', 'modifier_name': 'AcceptanceBevel'}})
        code = '''import os, hashlib
from mathutils import Vector
obj=bpy.data.objects['RemoteB_Acceptance_Cube']
obj['remote_b_acceptance']=True
path=os.path.join(output_dir,'RemoteB_Blender_Acceptance.blend')
assert not os.path.exists(path), 'Refusing overwrite'
bpy.ops.wm.save_as_mainfile(filepath=path)
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=4
scene.render.threads_mode='FIXED'
scene.render.threads=2
scene.render.resolution_x=320
scene.render.resolution_y=240
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.filepath=os.path.join(output_dir,'preview.png')
bpy.ops.render.render(write_still=True)
result={'saved':path,'bytes':os.path.getsize(path),'sha256':hashlib.sha256(open(path,'rb').read()).hexdigest(),'objects':len(scene.objects),'render':scene.render.filepath,'render_bytes':os.path.getsize(scene.render.filepath)}
'''
        saved = submit({'action': 'script', 'code': code, 'timeout_seconds': 120})
        evidence = saved['value']
        assert Path(evidence['saved']).is_file() and evidence['bytes'] > 1000
        assert evidence['render_bytes'] > 100
        image = submit({'action': 'image', 'file': 'preview.png'})
        attachment = client.get('/api/artifacts/'+image['artifacts'][0]['id'], headers=ah)
        assert attachment.status_code == 200
        # Reopen with bpy directly: ensure scene/object persisted, no startup-file scripts run.
        reopened = submit({'action': 'script', 'code': "bpy.ops.wm.open_mainfile(filepath=" + repr(evidence['saved']) + "); result={'saved_object_present':bool(bpy.data.objects.get('RemoteB_Acceptance_Cube')),'file':bpy.data.filepath}"})
        assert reopened['value']['saved_object_present']
        submit({'action': 'script', 'code': "log('before intentional failure'); raise ValueError('acceptance intentional failure')"}, expect_error=True)
        failed = results['jobs'][-1]
        assert 'intentional failure' in json.dumps(failed)
        # A deliberately delayed READ-ONLY script establishes timeout/late-result handling.
        submit({'action': 'script', 'code': 'import time; time.sleep(11); result={"late_read_only":True}', 'timeout_seconds': 10}, expect_error=True)
        state = submit({'action': 'state'})
        deadline = time.monotonic()+5
        while not state['can_resume'] and time.monotonic()<deadline:
            time.sleep(.3)
            state = submit({'action': 'state'})
        assert state['paused'] and state['can_resume'], state
        assert state['late_result']['value']['late_read_only']
        recovered = submit({'action': 'resume', 'pause_id': state['pause_id'], 'acknowledge_state': True})
        assert recovered['resumed']
        assert not submit({'action': 'state'})['paused']
        results['passed'] = True
        results['saved_evidence'] = evidence
        print(json.dumps({'passed': True, 'version': results['version'], 'mode': results['mode'], 'jobs': len(results['jobs']), 'evidence': evidence, 'report': str(directory/'acceptance.json')}))
    finally:
        (directory/'test-finished').touch()
        (directory/'stop.request').touch()
        process.wait(timeout=30)
        if worker:
            worker.wait(timeout=30)
            assert worker.returncode == 0
        if server:
            server.should_exit = True
        log.close()
        (directory/'acceptance.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        if not results.get('passed'):
            print('Actual Blender child log (last 60 lines):', flush=True)
            print('\n'.join((directory/'blender.log').read_text(encoding='utf-8',errors='replace').splitlines()[-60:]), flush=True)


if __name__ == '__main__':
    main()
