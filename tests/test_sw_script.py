import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'windows-b'))
from script_schema import validate_script_request
import sw_script


class ScriptTests(unittest.TestCase):
    def test_wire_validation_and_identical_schema(self):
        self.assertEqual((ROOT/'windows-b/script_schema.py').read_bytes(),
                         (ROOT/'linux-server/script_schema.py').read_bytes())
        for invalid in ({}, {'mode': []}, {'mode': 'inspect', 'code': ''},
                        {'mode': 'execute', 'code': 'if'}, {'mode': 'execute', 'code': 'x'*24001},
                        {'mode': 'inspect', 'timeout_seconds': True},
                        {'mode': 'inspect', 'timeout_seconds': 301}):
            with self.subTest(invalid=str(invalid)[:70]), self.assertRaises(ValueError):
                validate_script_request(invalid)
        self.assertEqual(len(validate_script_request({'mode':'execute', 'code':'result = {}'})), 64)

    def test_opt_out_prevents_spawn_and_files(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(sw_script.subprocess, 'Popen') as child:
            with self.assertRaises(PermissionError):
                sw_script.execute_script({'mode':'execute', 'code':'result = {}'}, {}, temp, Mock())
            child.assert_not_called()
            self.assertEqual(list(Path(temp).iterdir()), [])

    def payload(self, temp, code):
        path = Path(temp)
        (path/'request.json').write_text(json.dumps({'mode':'execute','code':code}), encoding='utf-8')
        (path/'context.json').write_text(json.dumps({'output_dir':temp,'part_template':'','assembly_template':''}))
        # Contract fixture, deliberately no SolidWorks or CAD success claim.
        sw = Mock()
        sw.ActiveDoc = None
        sw.RevisionNumber.return_value = 'fixture'
        sw_script.run_payload(path, connector=lambda: sw)
        return json.loads((path/'response.json').read_text(encoding='utf-8'))

    def test_real_python_execution_reports_result_and_bounded_log(self):
        with tempfile.TemporaryDirectory() as temp:
            answer = self.payload(temp, 'print("a" * 20000)\nresult = {"sum":sum(range(10))}')
            self.assertTrue(answer['ok'])
            self.assertEqual(answer['result'], {'sum':45})
            self.assertTrue(answer['log_truncated'])
            self.assertLessEqual(len(answer['log']), 6000)

    def test_failure_preserves_traceback_and_partial_log_without_success(self):
        with tempfile.TemporaryDirectory() as temp:
            answer = self.payload(temp, 'log("before failure")\nraise ValueError("probe failure")')
            self.assertFalse(answer['ok'])
            self.assertIn('ValueError: probe failure', answer['traceback'])
            self.assertIn('<remote-sw-script>', answer['traceback'])
            self.assertIn('before failure', answer['log'])
            self.assertNotIn('after', answer)

    def test_non_json_result_is_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(self.payload(temp, 'result = {"x": float("nan")}')['ok'])

    def test_timeout_preserves_child_and_blocks_subsequent_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(sw_script.subprocess, 'Popen') as spawn:
            child = spawn.return_value
            child.pid = 123
            child.wait.side_effect = subprocess.TimeoutExpired('fixture', 10)
            params = {'mode':'inspect', 'timeout_seconds':10}
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                sw_script.execute_script(params, {}, temp, Mock())
            self.assertTrue((Path(temp)/sw_script.LOCK).exists())
            child.kill.assert_not_called()
            child.terminate.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'paused'):
                sw_script.execute_script(params, {}, temp, Mock())
            self.assertEqual(spawn.call_count, 1)

    def test_child_env_excludes_relay_token_and_uses_separate_extraction(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(sw_script.subprocess, 'Popen') as spawn:
            child = spawn.return_value
            child.pid, child.returncode = 123, 0
            def finish(timeout):
                folder = next((Path(temp)/'script-runs').iterdir())
                request = json.loads((folder/'request.json').read_text())
                (folder/'response.json').write_text(json.dumps({'ok':True,
                    'script_sha256':validate_script_request(request), 'log':'secret-test-token'}))
            child.wait.side_effect = finish
            with patch.dict(os.environ, {'REMOTE_B_AGENT_TOKEN':'secret-test-token'}):
                result = sw_script.execute_script({'mode':'inspect'}, {'token':'secret-test-token'}, temp, Mock())
            self.assertNotIn('REMOTE_B_AGENT_TOKEN', spawn.call_args.kwargs['env'])
            self.assertEqual(spawn.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertEqual(result['log'], '[TOKEN REDACTED]')
            self.assertFalse((Path(temp)/sw_script.LOCK).exists())


if __name__ == '__main__':
    unittest.main()
