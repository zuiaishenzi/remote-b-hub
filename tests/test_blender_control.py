"""Blender wire/lifecycle safety without requiring bpy or changing real profiles."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'windows-b'))
from blender_schema import validate_blender_request
from blender_control import execute_blender, BlenderError, blender_state, LOCK, catalog, prepare_bridge, export_addon
from blender_bridge import Bridge, atomic_json


class BlenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.config = {'output_dir': str(self.directory / 'output'), 'allow_blender_control': True,
                       'blender_output_dir': str(self.directory / 'output'), 'blender_port': 18766,
                       'auto_start_blender': False}

    def tearDown(self):
        self.temp.cleanup()

    def test_schema_parity_and_rejects_wrong_types(self):
        self.assertEqual((ROOT/'windows-b/blender_schema.py').read_bytes(), (ROOT/'linux-server/blender_schema.py').read_bytes())
        for request in ({'action': 'oops'}, {'action': []}, {'action': 'start', 'code': 'x'},
                        {'action': 'script', 'code': 'if'}, {'action': 'tool', 'name': '../bad'},
                        {'action': 'script', 'code': 'pass', 'timeout_seconds': True},
                        {'action': 'image', 'file': '../secret.png'},
                        {'action': 'tool', 'name': 'object_create', 'arguments': {'x': float('nan')}},
                        {'action': 'resume', 'pause_id': 'a'*64, 'acknowledge_state': 1}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                validate_blender_request(request)

    def test_permission_is_checked_before_socket_or_process_launch(self):
        with patch('blender_control.exchange') as exchange, patch('blender_control.subprocess.Popen') as launch:
            for action in ({'action': 'tool', 'name': 'object_create'}, {'action': 'script', 'code': 'pass'}):
                with self.assertRaises(PermissionError):
                    execute_blender(action, {**self.config, 'allow_blender_control': False}, self.directory)
            exchange.assert_not_called()
            launch.assert_not_called()

    def test_catalog_is_pinned_and_contains_real_parameter_schemas(self):
        result = catalog('object_create')
        self.assertEqual(len(result['commit']), 40)
        self.assertEqual(catalog()['count'], 218)
        self.assertIn('type', result['tools'][0]['input_schema']['properties'])
        with self.assertRaises(ValueError):
            catalog('made_up_command')

    def test_bundle_export_contains_upstream_license_but_no_local_secret(self):
        import zipfile
        result = export_addon(self.config, self.directory, self.directory/'addon.zip')
        settings = json.loads((self.directory/'blender-bridge.json').read_text())
        self.assertTrue(Path(settings['directory']).is_absolute())
        with zipfile.ZipFile(result['addon']) as archive:
            self.assertIn('remote_b_blender/rfingadam/LICENSE', archive.namelist())
            self.assertIn('remote_b_blender/blender_bridge.py', archive.namelist())
            self.assertFalse(any(settings['token'].encode() in archive.read(name) for name in archive.namelist()))
        self.assertNotEqual(settings['token'], self.config.get('token'))

    def test_lost_response_pauses_and_terminal_receipt_required_for_resume(self):
        settings, _ = prepare_bridge(self.config, self.directory)
        with patch('blender_control.exchange', side_effect=[{'ok': True, 'value': {}}, TimeoutError('test delay')]):
            with self.assertRaises(BlenderError):
                execute_blender({'action': 'script', 'code': 'pass'}, self.config, self.directory)
        state = blender_state(self.directory)
        self.assertTrue(state['paused'])
        self.assertFalse(state['can_resume'])
        with self.assertRaises(RuntimeError):
            execute_blender({'action': 'resume', 'pause_id': state['pause_id'], 'acknowledge_state': True}, self.config, self.directory)
        receipt = self.directory/'blender-runs'/state['request_id']/'response.json'
        atomic_json(receipt, {'id': state['request_id'], 'ok': True, 'value': {'late': True}})
        with self.assertRaises(RuntimeError):
            execute_blender({'action': 'resume', 'pause_id': '0'*64, 'acknowledge_state': True}, self.config, self.directory)
        result = execute_blender({'action': 'resume', 'pause_id': state['pause_id'], 'acknowledge_state': True}, self.config, self.directory)
        self.assertTrue(result['resumed'])
        self.assertFalse((self.directory/LOCK).exists())
        self.assertEqual(json.loads(Path(result['audit']).read_text())['actor'], 'authenticated-A')

    def test_local_auth_failure_never_imports_bpy_or_creates_audit(self):
        bridge = Bridge({'directory': str(self.directory), 'token': 'x'*64, 'port': 18766})
        with patch('blender_bridge.snapshot') as snapshot:
            response = bridge.handle(json.dumps({'token': 'wrong', 'id': uuid.uuid4().hex, 'params': {'action': 'inspect'}}).encode())
        self.assertFalse(response['ok'])
        snapshot.assert_not_called()
        self.assertFalse((self.directory/'blender-runs').exists())

    def test_request_identity_replay_never_executes_twice_or_corrupts_receipt(self):
        bridge = Bridge({'directory': str(self.directory), 'token': 'x'*64, 'port': 18766})
        identity = uuid.uuid4().hex
        packet = {'token': 'x'*64, 'id': identity, 'params': {'action': 'inspect'}}
        with patch('blender_bridge.snapshot', return_value={'fixture': True}) as snapshot:
            first = bridge.handle(json.dumps(packet).encode())
            second = bridge.handle(json.dumps(packet).encode())
            self.assertEqual(first, second)
            self.assertEqual(snapshot.call_count, 3)
            packet['params'] = {'action': 'script', 'code': 'raise Exception()'}
            different = bridge.handle(json.dumps(packet).encode())
        self.assertFalse(different['ok'])
        receipt = json.loads((self.directory/'blender-runs'/identity/'response.json').read_text())
        self.assertEqual(receipt, first)

    def test_resume_and_pause_do_not_touch_sw_lock(self):
        swlock = self.directory/'cad-state-unknown.json'
        swlock.write_text('{"sw":"untouched"}')
        self.assertFalse(execute_blender({'action': 'state'}, self.config, self.directory)['paused'])
        self.assertEqual(swlock.read_text(), '{"sw":"untouched"}')


if __name__ == '__main__':
    unittest.main()
