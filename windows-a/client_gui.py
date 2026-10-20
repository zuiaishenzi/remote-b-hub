"""A-side configuration, diagnostics and explicitly enabled remote SW scripts."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows-b'))
from desktop_config import protect_token, unprotect_token, redact
from relay_client import RelayClient


class ClientWindow:
    def __init__(self, root, directory):
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
        self.job_id = tk.StringVar()
        self.artifact_id = tk.StringVar()
        root.title('Remote B Hub — A 端控制台')
        root.geometry('1000x760')
        panel = ttk.Frame(root, padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='A 端：安全配置、启动 Codex、任务与截图', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w', pady=(0, 12))
        fields = ttk.Frame(panel)
        fields.pack(fill='x')
        fields.columnconfigure(1, weight=1)
        for row, (key, label) in enumerate((('server_url', 'NAS 服务入口'), ('token', 'A Token / HUB_A_TOKEN'), ('workspace', 'A 仓库工作目录'))):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            ttk.Entry(fields, textvariable=self.variables[key], show='*' if key == 'token' else '').grid(row=row, column=1, sticky='ew', pady=4)
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=8)
        for label, callback in (('保存配置', self.save), ('启动 Codex', self.start_codex),
                                ('建模技能', self.open_skills),
                                ('SW 脚本', self.open_script),
                                ('检查更新', self.open_update),
                                ('检查 B 在线状态', lambda: self.call('status', lambda c: c.request('GET', '/api/status'))),
                                ('请求 SW 截图', lambda: self.call('submitted', lambda c: c.request('POST', '/api/jobs', {'operation': 'screenshot'})))):
            ttk.Button(buttons, text=label, command=callback).pack(side='left', padx=(0, 8))
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=6)
        ttk.Label(row, text='任务 ID').pack(side='left')
        ttk.Entry(row, textvariable=self.job_id, width=44).pack(side='left', padx=6)
        ttk.Button(row, text='读取任务/错误', command=self.read_job).pack(side='left', padx=6)
        ttk.Button(row, text='列出截图附件', command=self.list_images).pack(side='left')
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=6)
        ttk.Label(row, text='截图附件').pack(side='left')
        self.artifacts = ttk.Combobox(row, textvariable=self.artifact_id, width=55, state='readonly')
        self.artifacts.pack(side='left', padx=6)
        ttk.Button(row, text='下载并查看', command=self.open_image).pack(side='left')
        self.output = scrolledtext.ScrolledText(panel, wrap='word', font=('Consolas', 10), state='disabled')
        self.output.pack(fill='both', expand=True, pady=8)
        ttk.Label(panel, text='截图通过 A Token 下载到本机；实时视频/远控需另行配置。启动 Codex 需已有 CLI 与 pc-b 注册。').pack(anchor='w')
        root.after(200, self.tick)

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
            self.output.configure(state='normal')
            self.output.insert('end', redact(text, self.variables['token'].get()) + '\n')
            self.output.see('end')
            self.output.configure(state='disabled')
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
        client_window = ClientWindow(root, directory)
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
