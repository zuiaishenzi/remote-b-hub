"""Shared nonblocking Tk update dialog; update helpers never touch saved credentials."""
import json
import queue
import sys
import threading

from desktop_update import check_update, stage_update, launch_helper
from desktop_version import runtime_info


class UpdateWindow:
    def __init__(self, root, directory, product, prepare=None):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        self.directory, self.product, self.prepare = directory, product, prepare
        self.window = tk.Toplevel(root)
        self.window.title('检查更新 — ' + ('A 端' if product == 'a' else 'B 端'))
        self.window.geometry('700x410')
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill='both', expand=True)
        current = runtime_info()
        self.current = current
        ttk.Label(panel, text='当前版本：' + current.get('release_tag', current.get('source_commit', '源码运行'))).pack(anchor='w')
        ttk.Label(panel, text='更新源：GitHub / zuiaishenzi/remote-b-hub；仅稳定 Release。').pack(anchor='w', pady=5)
        self.output = scrolledtext.ScrolledText(panel, height=12, wrap='word')
        self.output.pack(fill='both', expand=True, pady=6)
        ttk.Label(panel, text='保留已保存的 Token、模板、输出路径。安装时退出并自动重启；旧 EXE 保留备份。').pack(anchor='w')
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=8)
        self.check_button = ttk.Button(row, text='检查最新版本', command=self.check)
        self.check_button.pack(side='left')
        self.install_button = ttk.Button(row, text='下载并更新', command=self.install, state='disabled')
        self.install_button.pack(side='left', padx=8)
        self.results = queue.Queue()
        self.release = None
        self.window.after(200, self.tick)
        if not getattr(sys, 'frozen', False):
            self.write('当前以源码运行，可检查版本；请用 git pull 更新源码。EXE 版本支持自动替换。')

    def write(self, message):
        self.output.insert('end', str(message) + '\n')
        self.output.see('end')

    def run(self, kind, action):
        self.check_button.configure(state='disabled')
        self.install_button.configure(state='disabled')
        def worker():
            try:
                self.results.put((kind, action()))
            except Exception as exc:
                self.results.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def check(self):
        self.write('正在读取稳定版及 SHA256 清单……')
        self.run('checked', lambda: check_update(self.product, self.current))

    def install(self):
        if not self.release or not self.release['available'] or not getattr(sys, 'frozen', False):
            return
        self.write('下载、校验并运行新版隔离自检；此阶段不会退出当前程序……')
        self.run('staged', lambda: stage_update(self.release, self.directory))

    def tick(self):
        if not self.window.winfo_exists():
            return
        while not self.results.empty():
            kind, value = self.results.get_nowait()
            self.check_button.configure(state='normal')
            if kind == 'checked':
                self.release = value
                self.write(json.dumps({k: value[k] for k in ('available', 'tag', 'source_commit', 'size')}, ensure_ascii=False, indent=2))
                if value['available'] and getattr(sys, 'frozen', False):
                    self.install_button.configure(state='normal')
                else:
                    self.write('无需更新。' if not value['available'] else '源码请通过 Git 更新。')
            elif kind == 'staged':
                try:
                    if self.prepare:
                        self.prepare(value)
                    else:
                        launch_helper(value)
                        self.window.master.destroy()
                    return
                except Exception as exc:
                    self.write('未启动更新：' + str(exc))
            else:
                self.write('更新未完成：' + str(value))
                self.write('原 EXE 和已保存的设置保持不变。')
        self.window.after(200, self.tick)
