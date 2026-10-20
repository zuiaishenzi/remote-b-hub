"""Real frozen bootstrap/replacement/restart using disposable A/B install folders.

Only build fixtures are replaced. No user EXE/settings or SolidWorks session is touched.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'windows-b'))
from desktop_update import sha256
from desktop_config import protect_token


def verify(executable, product):
    executable=Path(executable).resolve()
    with tempfile.TemporaryDirectory(prefix='update-smoke-',dir=ROOT/'build') as tmp, \
            tempfile.TemporaryDirectory(prefix='remote-b-update-data-') as temporary_data:
        root=Path(tmp)
        data=Path(temporary_data)
        stage=data/'updates'/'test'
        stage.mkdir(parents=True)
        install=root/'install with spaces'
        install.mkdir()
        target=install/executable.name
        old=ROOT/'build/update-old-fixtures'/executable.name
        shutil.copy2(old if old.is_file() else executable,target)
        old_hash=sha256(target)
        settings={'server_url':'','token_dpapi':protect_token('update-smoke-dummy-token-'+'x'*32),
                  'workspace':str(root),'auto_start_agent':False}
        config=data/'config.json'
        config.write_text(json.dumps(settings),encoding='utf-8')
        before=config.read_bytes()
        shutil.copy2(executable,stage/'payload.exe')
        shutil.copy2(executable,stage/'updater.exe')
        env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'}
        original=subprocess.Popen([str(target),'--smoke-test','--data-dir',str(data)],env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        plan={'product':product,'target':str(target),'old_sha256':old_hash,'sha256':sha256(executable),
              'data_directory':str(data),'wait_pids':[original.pid],'tag':'desktop-999999-1',
              'resume_agent':False,'restart_smoke_test':True}
        (stage/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        helper=subprocess.Popen([str(stage/'updater.exe'),'--apply-update',str(stage/'plan.json')],env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert helper.wait(timeout=90)==0
        assert original.wait(timeout=10)==0
        result=json.loads((data/'update-result.json').read_text())
        assert result['ok'],result
        assert sha256(target)==sha256(executable)
        assert sha256(result['backup'])==old_hash
        assert config.read_bytes()==before
        marker=data/('client-smoke.json' if product=='a' else 'gui-smoke.json')
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            try:
                if json.loads(marker.read_text()).get('updater_support'): break
            except (OSError,ValueError): pass
            time.sleep(.25)
        else: raise AssertionError('Restarted updated EXE did not complete GUI self-test')
        # The restarted one-file bootloader may still be releasing its image.
        time.sleep(1)
        print('PASS: real frozen '+product+' wait/replace/backup/restart/config preservation')


if __name__=='__main__':
    verify(sys.argv[1],'a')
    verify(sys.argv[2],'b')
