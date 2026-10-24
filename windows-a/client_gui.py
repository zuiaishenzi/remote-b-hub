"""A-side configuration, diagnostics and explicitly enabled remote SW scripts."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows-b'))
from desktop_config import protect_token, unprotect_token, redact
from relay_client import RelayClient


class ClientWindow:
    def __init__(self, root, directory, smoke=False):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        self.root, self.directory = root, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue()
        self.picture = None
        values = {'server_url': os.environ.get('REMOTE_B_API_URL', ''),
                  'token': os.environ.get('REMOTE_B_CLIENT_TOKEN', ''), 'workspace': r'C:\RemoteB\remote-b-hub'}
        path = self.directory / 'config.json'
        if path.exists():
            stored = json.loads(path.read_text(encoding='utf-8'))
            values.update(server_url=stored['server_url'], workspace=stored['workspace'], token=unprotect_token(stored['token_dpapi']))
        self.variables = {key: tk.StringVar(value=value) for key, value in values.items()}
        self.saved_connection = {'server_url': values['server_url'], 'token': values['token']}
        self.job_id = tk.StringVar()
        self.artifact_id = tk.StringVar()
        self._status_busy = False
        self.smoke = smoke
        from client_view import build_client
        build_client(self)
        if not smoke:
            root.after(500, self.poll_status)
        root.after(200, self.tick)

    def refresh_status(self, saved=False):
        if self._status_busy:
            return
        try:
            if saved:
                if not self.saved_connection['server_url'] or len(self.saved_connection['token']) < 32:
                    raise ValueError('No saved connection')
                client = RelayClient(self.saved_connection['server_url'], self.saved_connection['token'])
            else:
                client = self.client()
        except Exception:
            self.connection_card.set('未配置', '请前往设置页保存连接信息', 'warn')
            self.shell.footer.set('尚未配置连接 · 请先完成设置')
            return
        self._status_busy = True
        def run():
            try:
                self.queue.put(('status', client.request('GET', '/api/status')))
            except Exception as exc:
                self.queue.put(('connection_error', redact(str(exc), client.token)))
            finally:
                self.queue.put(('status_finished', None))
        threading.Thread(target=run, daemon=True).start()

    def poll_status(self):
        self.refresh_status(saved=True)
        self.root.after(10000, self.poll_status)

    def open_cad_control(self):
        from cad_control_window import CadControlWindow
        return CadControlWindow(self)

    def open_script(self):
        from script_window import ScriptWindow
        return ScriptWindow(self)

    def open_skills(self):
        from cad_skill_window import SkillWindow
        return SkillWindow(self)

    def open_update(self):
        from update_window import UpdateWindow
        return UpdateWindow(self.root, self.directory, 'a')

    def client(self):
        server, token = self.variables['server_url'].get().rstrip('/'), self.variables['token'].get()
        url = urlsplit(server)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('NAS 地址不合法')
        if len(token) < 32 or any(c.isspace() for c in token):
            raise ValueError('请输入 NAS 的 HUB_A_TOKEN 值')
        return RelayClient(server, token)

    def save(self):
        from tkinter import messagebox
        try:
            client = self.client()
            stored = {'server_url': client.server, 'token_dpapi': protect_token(client.token), 'workspace': self.variables['workspace'].get()}
            path = self.directory / 'config.json'
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
            self.saved_connection = {'server_url': client.server, 'token': client.token}
            self.queue.put(('message', '配置已按当前 Windows 用户加密保存。'))
            return True
        except Exception as exc:
            messagebox.showerror('未保存', redact(str(exc), self.variables['token'].get()))
            return False

    def start_codex(self):
        if not self.save():
            return
        workspace = Path(self.variables['workspace'].get())
        if not workspace.is_dir():
            self.queue.put(('message', '仓库工作目录不存在，请先设置正确目录。'))
            return
        client = self.client()
        env = {**os.environ, 'REMOTE_B_API_URL': client.server, 'REMOTE_B_CLIENT_TOKEN': client.token}
        subprocess.Popen(['powershell.exe', '-NoProfile', '-NoExit', '-Command', 'codex'], cwd=str(workspace),
                         env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.queue.put(('message', '已打开配置好 A 环境变量的 Codex 窗口；使用 /mcp 核对 pc-b。'))

    def call(self, kind, callback):
        try:
            client = self.client()
        except Exception as exc:
            self.queue.put(('message', str(exc)))
            return
        def run():
            try:
                self.queue.put((kind, callback(client)))
            except Exception as exc:
                self.queue.put(('message', redact(str(exc), client.token)))
        threading.Thread(target=run, daemon=True).start()

    def read_job(self):
        import uuid
        try:
            job_id = str(uuid.UUID(self.job_id.get()))
        except ValueError:
            self.queue.put(('message', '请填写合法任务 UUID'))
            return
        self.call('job', lambda c: c.request('GET', '/api/jobs/' + job_id))

    def list_images(self):
        import uuid
        try:
            job_id = str(uuid.UUID(self.job_id.get()))
        except ValueError:
            self.queue.put(('message', '请填写合法任务 UUID'))
            return
        self.call('artifacts', lambda c: c.request('GET', '/api/jobs/' + job_id + '/artifacts'))

    def open_image(self):
        identity = self.artifact_id.get()
        self.call('image', lambda c: c.download(identity, self.directory / 'artifacts'))

    def tick(self):
        import tkinter as tk
        from tkinter import ttk
        while not self.queue.empty():
            kind, value = self.queue.get_nowait()
            if kind == 'submitted':
                self.job_id.set(value['job_id'])
                self.task_card.set('已排队', value['job_id'][:18], 'busy')
                self.shell.footer.set('任务已提交 · 请读取真实结果')
            elif kind == 'status_finished':
                self._status_busy = False
                continue
            elif kind == 'status':
                online = value.get('online', False)
                self.connection_card.set('在线' if online else '离线',
                    f"等待任务 {value.get('queued_jobs', 0)} 个 · 心跳 {value.get('last_seen_seconds_ago')} 秒前" if online else '未收到近期代理心跳',
                    'good' if online else 'warn')
                self.shell.footer.set('B 在线 · '+time.strftime('%H:%M:%S')+' 检查' if online else 'B 离线 · 请检查 B 端代理')
                continue
            elif kind == 'connection_error':
                self.connection_card.set('连接异常', '详见日志；检查 NAS 地址与凭据', 'bad')
                self.shell.footer.set('连接检查失败 · 详见日志')
            elif kind == 'job':
                status = value.get('status', 'unknown')
                self.task_card.set({'done':'已完成','error':'失败','running':'执行中','queued':'已排队'}.get(status,status),
                    value.get('job_id','')[:18], 'good' if status=='done' else ('bad' if status=='error' else 'busy'))
                result = (value.get('result') or {}).get('value',{})
                sw = result if result.get('connected') else result.get('after',{})
                if sw.get('connected'):
                    self.sw_card.set('已连接', 'COM '+str(sw.get('revision','未知'))+' · '+time.strftime('%H:%M:%S')+' 查询', 'good')
                if status=='error':
                    self.shell.footer.set('任务失败 · 请在日志页查看完整诊断')
            elif kind == 'artifacts':
                identities = [a['id'] for a in value['artifacts']]
                self.artifacts['values'] = identities
                self.artifact_id.set(identities[0] if identities else '')
            elif kind == 'image':
                from PIL import Image, ImageTk
                try:
                    with Image.open(value['downloaded']) as picture:
                        picture.thumbnail((1100, 750))
                        photo = ImageTk.PhotoImage(picture.copy())
                    window = tk.Toplevel(self.root)
                    window.title('SW 截图 — ' + value['sha256'][:12])
                    label = ttk.Label(window, image=photo)
                    label.image = photo
                    label.pack()
                except Exception as exc:
                    value = '图片无法显示：' + str(exc)
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
            text = time.strftime('%H:%M:%S ') + redact(redact(text, self.variables['token'].get()), self.saved_connection['token']) + '\n'
            self.log_view.append(text)
            from desktop_ui import append_event_log
            append_event_log(self.directory / 'client.log', text)
        self.root.after(200, self.tick)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--data-dir')
    parser.add_argument('--apply-update')
    args = parser.parse_args()
    if args.apply_update:
        from desktop_update import apply_update
        return apply_update(args.apply_update)
    directory = Path(args.data_dir) if args.data_dir else Path(os.environ['LOCALAPPDATA']) / 'RemoteBHubA'
    try:
        import tkinter as tk
        root = tk.Tk()
        if args.smoke_test:
            root.withdraw()
        client_window = ClientWindow(root, directory, smoke=args.smoke_test)
        if args.smoke_test:
            from cad_skills import catalog, plan_part, install_project_skills
            assert len(catalog()['skills']) == 3
            for template in catalog()['templates']:
                plan_part(template, {}, 'Smoke_' + template)
            skill_window = client_window.open_skills()
            skill_window.window.withdraw()
            skill_window.plan()
            update_window = client_window.open_update()
            update_window.window.withdraw()
            script_window = client_window.open_script()
            script_window.window.withdraw()
            control_window = client_window.open_cad_control()
            control_window.window.withdraw()
            install_project_skills(directory)
            from desktop_config import protect_token, unprotect_token
            assert unprotect_token(protect_token('a-side-build-test')) == 'a-side-build-test'
            root.after(700, root.destroy)
        root.mainloop()
        if args.smoke_test:
            (directory / 'client-smoke.json').write_text('{"ok":true,"updater_support":true}', encoding='utf-8')
        return 0
    except Exception:
        import traceback
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'startup-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
