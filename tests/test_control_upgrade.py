"""Local contracts, relay auth, attachment roundtrip and launcher lifecycle.

C# uses a compile-only PIA stub: this is NOT a SolidWorks acceptance test.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ('windows-b', 'windows-a', 'linux-server')]
from control_schema import validate_document_request
from interop_control import managed_path
from artifact_store import ArtifactStore
from relay_client import RelayClient
import desktop_launcher as launcher


def png():
    from PIL import Image
    stream = io.BytesIO()
    Image.new('RGB', (12, 8), 'blue').save(stream, format='PNG')
    return stream.getvalue()


class ControlTests(unittest.TestCase):
    def test_schema_is_identical_on_server_and_worker(self):
        self.assertEqual((ROOT/'windows-b/control_schema.py').read_bytes(),
                         (ROOT/'linux-server/control_schema.py').read_bytes())

    def test_document_schema_rejects_code_and_unsafe_paths(self):
        for params in ({'action': []}, {'action': 'powershell'}, {'action': 'inspect', 'code': 'x'},
                       {'action': 'close'}, {'action': 'open', 'file': '../x.SLDPRT'},
                       {'action': 'save_copy', 'file': 'x.SLDPRT', 'new_file': 'X.SLDPRT'},
                       {'action': 'save_copy', 'file': 'x.SLDPRT', 'new_file': 'x.SLDASM'},
                       {'action': 'inspect', 'new_file': 'x.SLDPRT'}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                validate_document_request(params)
        validate_document_request({'action': 'inspect'})
        validate_document_request({'action': 'save_copy', 'file': 'x.SLDPRT', 'new_file': 'y.SLDPRT'})

    def test_paths_require_existing_input_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'x.SLDPRT').write_bytes(b'example')
            self.assertEqual(managed_path(tmp, 'x.SLDPRT'), Path(tmp)/'x.SLDPRT')
            with self.assertRaises(FileExistsError): managed_path(tmp, 'x.SLDPRT', False)
            with self.assertRaises(FileNotFoundError): managed_path(tmp, 'missing.SLDPRT')
            with self.assertRaises(ValueError): managed_path(tmp, '../x.SLDPRT')

    @unittest.skipUnless(os.name == 'nt', 'Windows Framework compiler')
    def test_csharp_compiles_and_contract_runs_without_com(self):
        # These empty interfaces validate syntax only. No CAD operations are simulated.
        compiler = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.is_file(): self.skipTest('Framework compiler not installed')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stub = tmp/'stub.cs'
            stub.write_text('namespace SolidWorks.Interop.sldworks { public interface ISldWorks {} '
                'public interface IModelDoc2 { new int GetType(); } '
                'public interface IAssemblyDoc { object GetComponents(bool top); } '
                'public interface IPartDoc { object GetBodies2(int type, bool visible); }}')
            library = tmp/'SolidWorks.Interop.sldworks.dll'
            build = subprocess.run([str(compiler), '/nologo', '/target:library', '/out:'+str(library), str(stub)], capture_output=True)
            self.assertEqual(build.returncode, 0, build.stdout.decode(errors='replace'))
            target = tmp/'control.exe'
            build = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(ROOT/'windows-b/interop/BuildInterop.ps1'), '-InteropDirectory', str(tmp),
                '-DestinationExe', str(target)], capture_output=True)
            self.assertEqual(build.returncode, 0, (build.stdout+build.stderr).decode(errors='replace'))
            run = subprocess.run([str(target), '--contract-test'], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout.decode(errors='replace'))
            self.assertIn('save_copy', json.loads(run.stdout.decode('utf-8-sig'))['actions'])


class LauncherCloseTests(unittest.TestCase):
    def app(self, directory):
        app = launcher.Launcher.__new__(launcher.Launcher)
        app.directory, app.root, app.process = Path(directory), Mock(), Mock()
        app.want_agent, app.message = True, Mock()
        return app

    def test_one_close_exits_gui_even_while_worker_is_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.app(tmp)
            app.process.poll.return_value = None
            app.quit()
            app.root.destroy.assert_called_once()
            self.assertTrue((Path(tmp)/'stop.request').exists())
            self.assertFalse(app.want_agent)
            app.process.terminate.assert_not_called()
            app.process.kill.assert_not_called()

    def test_reopen_does_not_cancel_previous_stop_or_spawn_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.app(tmp)
            stop = Path(tmp)/'stop.request'
            stop.touch()
            with patch.object(launcher, 'worker_running', return_value=True), patch.object(launcher.subprocess, 'Popen') as spawn:
                app.spawn_worker()
            spawn.assert_not_called()
            self.assertTrue(stop.exists())

    def test_frozen_worker_has_independent_extraction_lifetime(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.app(tmp)
            with patch.object(launcher, 'worker_running', return_value=False), patch.object(launcher.subprocess, 'Popen') as spawn:
                app.spawn_worker()
            self.assertEqual(spawn.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')


class ArtifactTests(unittest.TestCase):
    def test_validation_quota_expiry_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(Path(tmp)/'db', Path(tmp)/'images')
            with self.assertRaises(ValueError): store.path('../private')
            with self.assertRaises(Exception): store.put('j', 'image/png', b'not an image')
            with self.assertRaises(ValueError): store.put('j', 'image/jpeg', png())
            with patch('artifact_store.MAX_STORE_BYTES', 1), self.assertRaises(ValueError):
                store.put('j', 'image/png', png())
            rows = [store.put('j', 'image/png', png()) for _ in range(3)]
            with self.assertRaises(ValueError): store.put('j', 'image/png', png())
            self.assertEqual(len(store.list('j')), 3)
            with store.connect() as db: db.execute('UPDATE artifacts SET expires=0')
            self.assertEqual(store.list('j'), [])
            self.assertFalse(store.path(rows[0]['id']).exists())

    def test_a_download_verifies_checksum_and_writes_actual_image(self):
        content = png()
        response = io.BytesIO(content)
        response.headers = {'Content-Type': 'image/png', 'X-Content-SHA256': hashlib.sha256(content).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.urlopen', return_value=response):
            result = RelayClient('https://example.test', 'a'*64).download('c'*48, tmp)
            self.assertEqual(Path(result['downloaded']).read_bytes(), content)
            self.assertTrue(result['image_requires_explicit_open'])
        response = io.BytesIO(content)
        response.headers = {'Content-Type': 'image/png', 'X-Content-SHA256': 'bad'}
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.urlopen', return_value=response), self.assertRaises(ValueError):
            RelayClient('https://example.test', 'a'*64).download('c'*48, tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class RelayTests(unittest.TestCase):
    def test_auth_job_lifecycle_and_binary_attachment_roundtrip(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'HUB_DB':str(Path(tmp)/'jobs.db'), 'HUB_A_TOKEN':'a'*64, 'HUB_B_TOKEN':'b'*64,
            'HUB_ARTIFACT_DIR':str(Path(tmp)/'attachments')}):
            spec = importlib.util.spec_from_file_location('upgrade_test_server', ROOT/'linux-server/server.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
                a, b = {'Authorization':'Bearer '+'a'*64}, {'Authorization':'Bearer '+'b'*64}
                with TestClient(module.app) as client:
                    self.assertEqual(client.get('/health').json()['protocol_version'], 2)
                    self.assertEqual(client.post('/api/jobs', headers=b, json={'operation':'screenshot'}).status_code, 401)
                    for params in ({'action':[]}, {'action':'inspect','code':'arbitrary'}, {'action':'close','file':'../x.SLDPRT'}):
                        self.assertEqual(client.post('/api/jobs', headers=a, json={'operation':'sw_document','params':params}).status_code, 400)
                    job = client.post('/api/jobs', headers=a, json={'operation':'screenshot'}).json()['job_id']
                    endpoint = '/agent/jobs/'+job+'/artifacts'
                    self.assertEqual(client.post(endpoint, headers={**b,'Content-Type':'image/png'}, content=png()).status_code, 409)
                    self.assertEqual(client.get('/agent/next', headers=b).json()['job']['job_id'], job)
                    self.assertEqual(client.post(endpoint, headers={**a,'Content-Type':'image/png'}, content=png()).status_code, 401)
                    self.assertEqual(client.post(endpoint, headers={**b,'Content-Type':'image/png'}, content=b'x'*(5*1024*1024+1)).status_code, 413)
                    reply = client.post(endpoint, headers={**b,'Content-Type':'image/png'}, content=png())
                    self.assertEqual(reply.status_code, 200, reply.text)
                    meta = reply.json()
                    url = '/api/artifacts/'+meta['id']
                    self.assertEqual(client.get(url).status_code, 401)
                    self.assertEqual(client.get(url, headers=b).status_code, 401)
                    image = client.get(url, headers=a)
                    self.assertEqual(image.content, png())
                    self.assertEqual(image.headers['x-content-sha256'], hashlib.sha256(png()).hexdigest())
                    self.assertEqual(client.get('/api/jobs/'+job+'/artifacts', headers=a).json()['artifacts'][0]['id'], meta['id'])
                    result = client.post('/agent/jobs/'+job+'/result', headers=b, json={'ok':True,'value':{'artifacts':[meta]}})
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(client.get('/api/jobs/'+job, headers=a).json()['status'], 'done')
            finally:
                sys.modules.pop(spec.name, None)


if __name__ == '__main__':
    unittest.main()
