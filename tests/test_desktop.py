"""Desktop config and queue worker tests. No actual SW or NAS is used."""
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows-b"))
import desktop_config as config
import desktop_worker as worker


class DesktopConfigTests(unittest.TestCase):
    def settings(self):
        return {**config.DEFAULTS, "server_url": "https://relay.example.test", "token": "test-secret-" * 4}

    def test_token_not_serialized_as_plaintext_and_settings_roundtrip(self):
        values = self.settings()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(config, "protect_token", return_value="encrypted-token"), patch.object(config, "unprotect_token", return_value=values["token"]):
                config.save_config(directory, values)
                raw = (Path(directory) / "config.json").read_text(encoding="utf-8")
                self.assertNotIn(values["token"], raw)
                self.assertNotIn('"token":', raw)
                self.assertEqual(config.load_config(directory), values)

    def test_invalid_credentials_and_url_are_rejected(self):
        for update in ({"token": "short"}, {"server_url": "https://user:pass@example.test"},
                       {"server_url": "file:///C:/file"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                config.validate_config({**self.settings(), **update})

    def test_redaction(self):
        self.assertEqual(config.redact("secret=actual-token", "actual-token"), "secret=[TOKEN REDACTED]")


class WorkerQueueTests(unittest.TestCase):
    def run_case(self, operation="ping", first_result_fails=False, execution_error=False, screenshots=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {**config.DEFAULTS, "server_url": "https://relay.example.test", "token": "sensitive-token-" * 3}
            settings["screenshots_enabled"] = screenshots
            calls = []
            result_attempts = 0
            answers = []
            def api(method, path, data=None):
                nonlocal result_attempts
                calls.append((method, path))
                if path == "/agent/next":
                    return {"job": {"job_id": "job-1", "operation": operation, "params": {}}}
                if path.endswith("/result"):
                    result_attempts += 1
                    if first_result_fails and result_attempts == 1:
                        raise OSError("network down")
                    answers.append(data)
                    (root / "stop.request").touch()
                return {"saved": True}
            def execute(op, params):
                print("[SW] stage test " + settings["token"])
                if execution_error:
                    raise RuntimeError("error " + settings["token"])
                return {"message": "ok"}
            modules = {
                "agent": types.SimpleNamespace(api=api),
                "diagnostic_agent": types.SimpleNamespace(execute=execute),
                "pythoncom": types.SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None),
                "win32api": types.SimpleNamespace(GetLastError=lambda: 0, CloseHandle=lambda h: None),
                "win32event": types.SimpleNamespace(CreateMutex=lambda *a: object()),
                "screen_capture": types.SimpleNamespace(capture_and_upload=Mock(side_effect=RuntimeError("capture unavailable"))),
            }
            with patch.dict(sys.modules, modules), patch.object(worker, "load_config", return_value=settings), \
                 patch.object(worker, "apply_environment"), patch.object(worker.time, "sleep"), \
                 patch.object(worker, "ensure_solidworks", return_value={"connected": True}) as ensure:
                self.assertEqual(worker.run_worker(root), 0)
            self.assertEqual(sum(path == "/agent/next" for _, path in calls), 1)
            self.assertFalse((root / "pending-result.json").exists())
            self.assertEqual(ensure.call_count, int(operation in worker.CAD_OPERATIONS))
            self.assertNotIn(settings["token"], (root / "agent.log").read_text(encoding="utf-8"))
            self.assertNotIn(settings["token"], json.dumps(answers))
            return answers[0]

    def test_ping_does_not_start_sw(self):
        self.assertTrue(self.run_case()["ok"])

    def test_cad_checks_sw_before_execution(self):
        self.assertTrue(self.run_case(operation="sw_recipe")["ok"])

    def test_result_retry_does_not_execute_same_task_again(self):
        self.assertTrue(self.run_case(first_result_fails=True)["ok"])

    def test_failure_reports_redacted_trace_and_logs(self):
        result = self.run_case(execution_error=True)
        self.assertFalse(result["ok"])
        self.assertIn("[TOKEN REDACTED]", result["diagnostics"]["traceback"])

    def test_screenshot_failure_preserves_original_cad_trace(self):
        result = self.run_case(operation="sw_recipe", execution_error=True, screenshots=True)
        self.assertFalse(result["ok"])
        self.assertIn("RuntimeError: error", result["diagnostics"]["traceback"])
        self.assertEqual(result["diagnostics"]["screenshot_error"], "capture unavailable")


class SolidWorksStartupTests(unittest.TestCase):
    def launch_case(self, already_starting=False, timeout=False, cancelled=False):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "SLDWORKS.exe"
            executable.touch()
            settings = {**config.DEFAULTS, "sw_exe": str(executable), "sw_start_timeout": 0 if timeout else 10}
            client = types.SimpleNamespace(GetObject=Mock())
            client.GetObject.return_value.ExecQuery.return_value = [object()] if already_starting else []
            modules = {"win32com": types.SimpleNamespace(client=client), "win32com.client": client,
                       "win32ts": types.SimpleNamespace(ProcessIdToSessionId=lambda pid: 1)}
            report = Mock()
            with patch.dict(sys.modules, modules), patch.object(worker, "sw_status", side_effect=[OSError("not running"), {"connected": True, "revision": "31.5"}]), \
                 patch.object(worker.subprocess, "Popen") as launch:
                if timeout or cancelled:
                    with self.assertRaises((TimeoutError, RuntimeError)):
                        worker.ensure_solidworks(settings, report, lambda: cancelled)
                else:
                    self.assertTrue(worker.ensure_solidworks(settings, report)["connected"])
                self.assertEqual(launch.call_count, int(not already_starting))

    def test_stopped_sw_is_launched_and_com_readiness_checked(self):
        self.launch_case()

    def test_starting_sw_process_is_not_duplicated(self):
        self.launch_case(already_starting=True)

    def test_sw_start_timeout_does_not_report_success(self):
        self.launch_case(timeout=True)

    def test_stop_during_sw_start_prevents_modeling(self):
        self.launch_case(cancelled=True)

    def test_running_sw_does_not_launch_another_process(self):
        with patch.object(worker, "sw_status", return_value={"connected": True}) as status, patch.object(worker.subprocess, "Popen") as launch:
            self.assertEqual(worker.ensure_solidworks(config.DEFAULTS, Mock()), {"connected": True})
        launch.assert_not_called()

    def test_disabled_auto_start_does_not_launch(self):
        with patch.object(worker, "sw_status", side_effect=OSError("not running")), patch.object(worker.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "未启用"):
                worker.ensure_solidworks({**config.DEFAULTS, "auto_start_sw": False}, Mock())
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
