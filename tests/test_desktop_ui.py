"""Isolated native GUI checks; never connect NAS, start workers or operate SW."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'windows-a'),str(ROOT/'windows-b')]


@unittest.skipUnless(os.name=='nt','Windows desktop UI')
class DesktopUiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root=tk.Tk()
        self.root.withdraw()
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)

    def tearDown(self):
        for callback in self.root.tk.call('after','info'):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.temp.cleanup()

    def app_a(self):
        from client_gui import ClientWindow
        return ClientWindow(self.root,self.directory,smoke=True)

    def test_navigation_preserves_unsaved_fields_and_keeps_logs(self):
        app=self.app_a()
        app.variables['workspace'].set('D:/Unsubmitted workspace')
        app.log_view.append('one retained event\n')
        for page in ('settings','logs','home'):
            app.shell.show(page)
            self.root.update_idletasks()
            self.assertEqual(app.shell.current,page)
            self.assertEqual(app.variables['workspace'].get(),'D:/Unsubmitted workspace')
        self.assertIn('one retained event',app.output.get('1.0','end'))
        self.assertFalse((self.directory/'config.json').exists())

    def test_log_filter_clear_and_persisted_redaction(self):
        app=self.app_a()
        secret='test-only-secret-'*3
        app.variables['token'].set(secret)
        app.queue.put(('message','连接成功 '+secret))
        app.queue.put(('message','任务失败：fixture'))
        app.tick()
        disk=(self.directory/'client.log').read_text(encoding='utf-8')
        self.assertNotIn(secret,disk)
        self.assertIn('[TOKEN REDACTED]',disk)
        app.log_view.query.set('失败')
        visible=app.output.get('1.0','end')
        self.assertIn('任务失败',visible)
        self.assertNotIn('连接成功',visible)
        app.log_view.clear()
        self.assertEqual((self.directory/'client.log').read_text(encoding='utf-8'),disk)

    def test_automatic_poll_does_not_send_unsaved_credentials(self):
        app=self.app_a()
        app.saved_connection={'server_url':'https://saved.example','token':'s'*64}
        app.variables['server_url'].set('https://edited.example')
        app.variables['token'].set('e'*64)
        with patch('client_gui.RelayClient') as relay,patch('client_gui.threading.Thread'):
            app.refresh_status(saved=True)
        relay.assert_called_once_with('https://saved.example','s'*64)

    def test_b_settings_scroll_and_existing_config_fields_survive_navigation(self):
        from desktop_launcher import Launcher
        from desktop_config import DEFAULTS
        with patch('desktop_launcher.worker_running',return_value=False):
            app=Launcher(self.root,self.directory,smoke=True)
            app.shell.show('settings')
            self.root.geometry('1000x720')
            self.root.deiconify()
            self.root.update()
            self.assertEqual(set(app.variables),set(DEFAULTS)-{'sw_start_timeout'})
            scroll=app.shell.scroll
            before=scroll.canvas.yview()[0]
            scroll.wheel(SimpleNamespace(widget=scroll.body,delta=-60))
            self.root.update_idletasks()
            self.assertGreater(scroll.canvas.yview()[0],before)
            app.variables['output_dir'].set('D:/Custom output')
            app.shell.show('home');app.shell.show('settings')
            self.assertEqual(app.variables['output_dir'].get(),'D:/Custom output')

    def test_application_icons_have_small_and_large_windows_sizes(self):
        from PIL import Image
        for name in ('RemoteBClient','RemoteBHub'):
            with Image.open(ROOT/'assets'/(name+'.ico')) as icon:
                self.assertTrue({(16,16),(32,32),(256,256)}<=icon.ico.sizes())

    def test_windows_state_reader_does_not_break_atomic_status_write(self):
        import json
        import threading
        import time
        from desktop_worker import write_json
        path=self.directory/'status.json'
        write_json(path,{'stage':'before'})
        reader=path.open('rb')
        errors=[]
        def publish():
            try:write_json(path,{'stage':'stopped'})
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=publish)
        thread.start()
        try:
            time.sleep(.08)
            self.assertTrue(thread.is_alive())
            self.assertEqual(json.loads(reader.read())['stage'],'before')
        finally:
            reader.close()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(json.loads(path.read_text())['stage'],'stopped')

    def test_switch_explicit_state_matches_boolean_setting(self):
        import tkinter as tk
        from desktop_ui import ToggleControl
        value=tk.BooleanVar(master=self.root,value=True)
        switch=ToggleControl(self.root,value)
        self.assertEqual(switch.state_label.get(),'已启用')
        self.assertFalse(int(switch.cget('indicatoron')))
        switch.invoke()
        self.assertFalse(value.get())
        self.assertEqual(switch.state_label.get(),'未启用')
        switch.invoke()
        self.assertTrue(value.get())
        self.assertEqual(switch.state_label.get(),'已启用')

    def test_agent_button_tracks_running_and_graceful_stop(self):
        from unittest.mock import Mock
        from desktop_launcher import Launcher
        with patch('desktop_launcher.worker_running',return_value=False):
            app=Launcher(self.root,self.directory,smoke=True)
            def start():
                app.process=Mock()
                app.process.poll.return_value=None
            with patch.object(app,'start',side_effect=start) as start_action, \
                 patch.object(app,'stop',wraps=app.stop) as stop_action:
                app.toggle_agent()
                start_action.assert_called_once()
                self.assertEqual(app.agent_toggle.cget('text'),'停止任务代理')
                app.toggle_agent()
                self.assertEqual(stop_action.call_count,1)
                self.assertEqual(app.agent_toggle.cget('text'),'正在停止…')
                self.assertTrue(app.agent_toggle.instate(['disabled']))
                app.toggle_agent()
                self.assertEqual(stop_action.call_count,1)
                app.process.poll.return_value=0
                app.sync_agent_control(False)
                self.assertEqual(app.agent_toggle.cget('text'),'启动任务代理')
                self.assertTrue(app.agent_toggle.instate(['!disabled']))

    def test_both_home_pages_fit_without_scroll_at_minimum_size(self):
        from desktop_launcher import Launcher
        from client_gui import ClientWindow
        for kind in ('b','a'):
            with self.subTest(kind=kind),patch('desktop_launcher.worker_running',return_value=False):
                if kind=='b':app=Launcher(self.root,self.directory,smoke=True)
                else:app=ClientWindow(self.root,self.directory,smoke=True)
                self.root.geometry('960x640')
                self.root.deiconify()
                self.root.update()
                self.assertLessEqual(app.shell.home.winfo_reqheight(),app.shell.home.winfo_height())
                def widgets(parent):
                    for child in parent.winfo_children():
                        yield child
                        yield from widgets(child)
                all_widgets=list(widgets(app.shell.home))
                self.assertFalse(any(w.winfo_class()=='Canvas' for w in all_widgets))
                self.assertFalse(any('最小化驻留' in str(w.cget('text')) for w in all_widgets if 'text' in w.keys()))
                for callback in self.root.tk.call('after','info'):self.root.after_cancel(callback)
                for child in self.root.winfo_children():child.destroy()


if __name__=='__main__':unittest.main()
