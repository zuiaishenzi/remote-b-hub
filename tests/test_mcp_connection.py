import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'windows-a'), str(ROOT/'windows-b')]
from mcp_connection import load_connection


class ConnectionTests(unittest.TestCase):
    def test_explicit_environment_wins_without_reading_profile(self):
        with patch('mcp_connection.unprotect_token') as decode:
            self.assertEqual(load_connection({'REMOTE_B_API_URL':'https://example.test/',
                'REMOTE_B_CLIENT_TOKEN':'a'*64}), ('https://example.test','a'*64))
            decode.assert_not_called()

    def test_partial_override_does_not_mix_server_and_saved_token(self):
        for env in ({'REMOTE_B_API_URL':'https://example.test'}, {'REMOTE_B_CLIENT_TOKEN':'a'*64}):
            with self.assertRaisesRegex(RuntimeError, 'partial'):
                load_connection(env)

    def test_desktop_restart_loads_encrypted_saved_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'RemoteBHubA/config.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'server_url':'https://example.test/', 'token_dpapi':'encrypted-fixture'}))
            with patch('mcp_connection.unprotect_token', return_value='a'*64) as decode:
                self.assertEqual(load_connection({'LOCALAPPDATA':temp}), ('https://example.test','a'*64))
                decode.assert_called_once_with('encrypted-fixture')

    def test_missing_or_unreadable_profile_has_actionable_error_without_secret(self):
        with self.assertRaisesRegex(RuntimeError, 'LOCALAPPDATA'):
            load_connection({})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'save NAS'):
                load_connection({'LOCALAPPDATA':temp})
            path=Path(temp)/'RemoteBHubA/config.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'server_url':'https://example.test','token_dpapi':'secret-fixture'}))
            with patch('mcp_connection.unprotect_token', side_effect=ValueError('secret-fixture')):
                with self.assertRaises(RuntimeError) as error:
                    load_connection({'LOCALAPPDATA':temp})
                self.assertNotIn('secret-fixture',str(error.exception))

    def test_invalid_url_and_token_refused(self):
        for url, token in [('https://user:password@example.test','a'*64),
                           ('file:///etc/passwd','a'*64), ('https://example.test?token=x','a'*64),
                           ('https://example.test','short'), ('https://example.test','a'*64+'\n')]:
            with self.assertRaises(RuntimeError):
                load_connection({'REMOTE_B_API_URL':url,'REMOTE_B_CLIENT_TOKEN':token})
