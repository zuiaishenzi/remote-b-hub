"""Updater metadata, tamper refusal, rollback and graceful shutdown contracts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import importlib.util
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'windows-b'))
import desktop_update as update
import desktop_launcher as launcher


class UpdateTests(unittest.TestCase):
    def test_release_manifest_is_generated_from_actual_file_bytes(self):
        spec=importlib.util.spec_from_file_location('manifest_writer',ROOT/'scripts/write-update-manifest.py')
        writer=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(writer)
        with tempfile.TemporaryDirectory() as tmp:
            for name in update.PRODUCTS.values():
                (Path(tmp)/name).write_bytes(b'MZ'+b'x'*1200)
            result=writer.write_manifest(tmp,'desktop-6-1','a'*40)
            self.assertEqual(result['assets']['RemoteBHub.exe']['sha256'],update.sha256(Path(tmp)/'RemoteBHub.exe'))
            self.assertEqual(result['assets']['RemoteBClient.exe']['size'],1202)
            with self.assertRaises(ValueError): writer.write_manifest(tmp,'bad','main')

    def metadata(self):
        data = b'MZ' + b'new-release' * 200
        release = {'tag_name': 'desktop-6-1', 'target_commitish': 'a'*40,
                   'assets': [{'name': n, 'size': len(data), 'browser_download_url':
                       'https://github.com/'+update.REPOSITORY+'/releases/download/desktop-6-1/'+n}
                       for n in ['RemoteBClient.exe','update-manifest.json']]}
        manifest = {'schema': 1, 'repository': update.REPOSITORY, 'tag': 'desktop-6-1',
                    'source_commit': 'a'*40, 'assets': {'RemoteBClient.exe': {
                        'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
        return data, release, manifest

    def check(self, release, manifest, current=None):
        with patch.object(update, 'fetch_bytes', side_effect=[json.dumps(release).encode(),json.dumps(manifest).encode()]):
            return update.check_update('a', current or {'release_tag': 'desktop-5-1','source_commit': 'b'*40})

    def test_matching_release_is_available_but_same_or_older_is_not(self):
        _, release, manifest = self.metadata()
        self.assertTrue(self.check(release,manifest)['available'])
        self.assertFalse(self.check(release,manifest,{'release_tag':'desktop-6-1','source_commit':'a'*40})['available'])
        self.assertFalse(self.check(release,manifest,{'release_tag':'desktop-7-1','source_commit':'b'*40})['available'])

    def test_mismatched_manifest_and_unsafe_urls_are_rejected(self):
        _, release, manifest = self.metadata()
        for mutation in [lambda m:m.update(repository='attacker/repo'),lambda m:m.update(source_commit='b'*40),
                         lambda m:m.update(tag='desktop-5-1'),
                         lambda m:m['assets']['RemoteBClient.exe'].update(sha256='invalid'),
                         lambda m:m['assets']['RemoteBClient.exe'].update(size=999999999)]:
            bad = copy.deepcopy(manifest)
            mutation(bad)
            with self.assertRaises(ValueError): self.check(release,bad)
        for url in ['http://github.com/'+update.REPOSITORY+'/releases/download/x/a',
                    'https://evil.example/a.exe','https://github.com/other/project/releases/download/x/a',
                    'https://user:secret@github.com/'+update.REPOSITORY+'/releases/download/x/a']:
            with self.assertRaises(ValueError): update.trusted_url(url, True)

    def test_bad_download_never_modifies_installed_exe_or_config(self):
        _, release, manifest = self.metadata()
        info = self.check(release,manifest)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/'RemoteBClient.exe'
            target.write_bytes(b'old executable fixture')
            config=root/'config.json'
            config.write_bytes(b'preserve encrypted local settings')
            with patch.object(update,'fetch_bytes',return_value=b'MZtampered'), self.assertRaises(ValueError):
                update.stage_update(info,root,target,self_test=False)
            self.assertEqual(target.read_bytes(),b'old executable fixture')
            self.assertEqual(config.read_bytes(),b'preserve encrypted local settings')

    def test_self_test_failure_does_not_exit_or_replace(self):
        data, release, manifest = self.metadata()
        info=self.check(release,manifest)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'RemoteBClient.exe'
            target.write_bytes(b'old')
            with patch.object(update,'fetch_bytes',return_value=data), patch.object(update.subprocess,'run',return_value=Mock(returncode=1)), self.assertRaises(RuntimeError):
                update.stage_update(info,tmp,target)
            self.assertEqual(target.read_bytes(),b'old')

    def test_replacement_keeps_exact_backup_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target,candidate=root/'RemoteBClient.exe',root/'payload.exe'
            target.write_bytes(b'old')
            candidate.write_bytes(b'new')
            (root/'config.json').write_bytes(b'dpapi-test-placeholder')
            backup=update.replace_checked(candidate,target,update.sha256(candidate),update.sha256(target))
            self.assertEqual(target.read_bytes(),b'new')
            self.assertEqual(backup.read_bytes(),b'old')
            self.assertEqual((root/'config.json').read_bytes(),b'dpapi-test-placeholder')

    def test_mid_install_failure_restores_old_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target,candidate=root/'RemoteBHub.exe',root/'payload.exe'
            target.write_bytes(b'old')
            candidate.write_bytes(b'new')
            original=Path.replace
            def fail_new(path,destination):
                if '.incoming-' in path.name: raise OSError('simulated disk failure')
                return original(path,destination)
            with patch.object(Path,'replace',fail_new),self.assertRaises(OSError):
                update.replace_checked(candidate,target,update.sha256(candidate),update.sha256(target))
            self.assertEqual(target.read_bytes(),b'old')

    def test_wait_timeout_never_replaces_or_kills_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            folder=directory/'updates'/'test'
            folder.mkdir(parents=True)
            target=directory/'RemoteBHub.exe'
            target.write_bytes(b'old')
            (folder/'plan.json').write_text(json.dumps({'product':'b','target':str(target),
                'data_directory':str(directory),'sha256':'a'*64,'wait_pids':[123456],'tag':'desktop-6-1'}))
            with patch.object(update,'wait_process',side_effect=TimeoutError('busy CAD worker')), patch.object(update,'replace_checked') as replace:
                self.assertEqual(update.apply_update(folder/'plan.json'),1)
                replace.assert_not_called()
            self.assertFalse(json.loads((directory/'update-result.json').read_text())['ok'])
            self.assertEqual(target.read_bytes(),b'old')

    def test_b_update_handoff_waits_for_own_worker_and_requests_graceful_stop(self):
        app=launcher.Launcher.__new__(launcher.Launcher)
        app.process=Mock(pid=123)
        app.process.poll.return_value=None
        app.quit=Mock()
        with patch.object(launcher,'worker_running',return_value=True),patch.object(update,'launch_helper') as launch:
            app.prepare_update('plan')
            launch.assert_called_once_with('plan',[123],resume_agent=True)
            app.quit.assert_called_once()
            app.process.kill.assert_not_called()
            app.process.terminate.assert_not_called()


if __name__=='__main__': unittest.main()
