import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'windows-b'))
import cad_control as control
from cad_control_schema import validate_cad_control


class CadControlTests(unittest.TestCase):
    def lock(self, folder, value=None):
        path=Path(folder)/control.LOCK
        path.write_text(json.dumps(value if value is not None else {'pid':111,'audit':'fixture'}))
        return path,hashlib.sha256(path.read_bytes()).hexdigest()

    def params(self, identity):
        return {'action':'resume','pause_id':identity,'acknowledge_state':True}

    def test_identical_contract_and_rejected_overrides(self):
        self.assertEqual((ROOT/'windows-b/cad_control_schema.py').read_bytes(),
                         (ROOT/'linux-server/cad_control_schema.py').read_bytes())
        for params in ({'action':[]},{'action':'kill'},{'action':'start','force':True},
                       {'action':'resume','pause_id':'a'*64,'acknowledge_state':False},
                       {'action':'resume','pause_id':'old','acknowledge_state':True}):
            with self.subTest(params=params),self.assertRaises(ValueError):
                validate_cad_control(params)

    def test_state_works_without_com_and_refuses_live_caller(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(control,'process_family',return_value=[111]):
            path,identity=self.lock(temp)
            self.assertTrue(control.cad_state(temp)['helper_running'])
            with self.assertRaisesRegex(RuntimeError,'still running'):
                control.resume_cad(self.params(identity),{'allow_sw_scripts':True},temp,Mock())
            self.assertTrue(path.exists())

    def test_stale_pause_and_disabled_control_cannot_unlock(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(control,'process_family',return_value=[]):
            path,identity=self.lock(temp)
            with self.assertRaises(PermissionError):
                control.resume_cad(self.params(identity),{},temp,Mock())
            with self.assertRaisesRegex(RuntimeError,'Pause changed'):
                control.resume_cad(self.params('0'*64),{'allow_sw_scripts':True},temp,Mock())
            self.assertTrue(path.exists())

    def test_dead_caller_recovery_is_audited_without_retry(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(control,'process_family',return_value=[]), \
             patch.object(control.subprocess,'Popen') as spawn:
            path,identity=self.lock(temp)
            result=control.resume_cad(self.params(identity),{'allow_sw_scripts':True},temp,Mock())
            self.assertTrue(result['resumed'])
            self.assertFalse(path.exists())
            archive=Path(temp)/'script-runs'/result['audit_id']
            self.assertTrue((archive/'previous-pause.json').exists())
            self.assertEqual(json.loads((archive/'recovery.json').read_text())['actor'],'authenticated-A')
            spawn.assert_not_called()

    def test_unknown_process_or_corrupt_record_fails_closed(self):
        for record in ({'audit':'no PID'},{'pid':True},{'pid':111}):
            with tempfile.TemporaryDirectory() as temp,patch.object(control,'process_family',side_effect=OSError('probe unavailable')):
                path,identity=self.lock(temp,record)
                self.assertFalse(control.cad_state(temp)['can_resume'])
                with self.assertRaises(RuntimeError):
                    control.resume_cad(self.params(identity),{'allow_sw_scripts':True},temp,Mock())
                self.assertTrue(path.exists())

    def test_start_is_blocked_before_spawn_if_paused_or_stopping(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(control.subprocess,'Popen') as spawn:
            self.lock(temp)
            with self.assertRaisesRegex(RuntimeError,'paused'):
                control.start_solidworks({},temp,Mock())
            spawn.assert_not_called()
        with tempfile.TemporaryDirectory() as temp,patch.object(control.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'stopping'):
                control.start_solidworks({},temp,Mock(),lambda:True)
            spawn.assert_not_called()

    def test_start_result_and_token_environment(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(control.subprocess,'Popen') as spawn:
            child=spawn.return_value
            child.pid,child.returncode=222,0
            def done():
                folder=next((Path(temp)/'script-runs').iterdir())
                (folder/'response.json').write_text(json.dumps({'ok':True,'value':{'connected':True,'revision':'fixture'}}))
                return 0
            child.poll.side_effect=done
            with patch.dict(os.environ,{'REMOTE_B_AGENT_TOKEN':'fixture-secret'}):
                result=control.start_solidworks({'sw_exe':'fixture.exe'},temp,Mock())
            self.assertTrue(result['connected'])
            self.assertNotIn('REMOTE_B_AGENT_TOKEN',spawn.call_args.kwargs['env'])
            self.assertEqual(spawn.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
            self.assertFalse((Path(temp)/control.LOCK).exists())

    def test_hung_start_retains_gate_without_killing_process(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(control.subprocess,'Popen') as spawn, \
             patch.object(control.time,'monotonic',side_effect=[0,1000]):
            child=spawn.return_value
            child.pid,child.poll.return_value=222,None
            with self.assertRaisesRegex(RuntimeError,'still running'):
                control.start_solidworks({'sw_exe':'fixture.exe'},temp,Mock())
            self.assertTrue((Path(temp)/control.LOCK).exists())
            child.terminate.assert_not_called()
            child.kill.assert_not_called()

    @unittest.skipUnless(os.name=='nt','Windows native process check')
    def test_actual_live_process_cannot_be_remotely_unlocked(self):
        child=subprocess.Popen([sys.executable,'-c','input()'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL)
        try:
            with tempfile.TemporaryDirectory() as temp:
                path,identity=self.lock(temp,{'pid':child.pid})
                self.assertTrue(control.cad_state(temp)['helper_running'])
                with self.assertRaises(RuntimeError):
                    control.resume_cad(self.params(identity),{'allow_sw_scripts':True},temp,Mock())
                self.assertTrue(path.exists())
        finally:
            child.communicate(b'\n',timeout=10)
