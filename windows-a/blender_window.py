"""A-side Blender console, using the same authenticated asynchronous task channel."""
import json
from blender_schema import validate_blender_request


class BlenderWindow:
    def __init__(self, owner):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        from desktop_ui import button
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title('Blender · 电脑 B')
        self.window.geometry('920x680')
        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Blender 远端控制', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='所有操作在 B 执行。脚本具有完整用户权限；读取状态后再分步修改。').pack(anchor='w', pady=(4, 12))
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        for label, action in [('检查连接', 'status'), ('启动 Blender', 'start'), ('读取场景', 'inspect'), ('检查暂停', 'state')]:
            button(actions, label, lambda a=action: self.send({'action': a})).pack(side='left', padx=(0, 8))
        notebook = ttk.Notebook(frame)
        notebook.pack(fill='both', expand=True, pady=12)
        script = ttk.Frame(notebook, padding=10)
        commands = ttk.Frame(notebook, padding=10)
        notebook.add(script, text='Python 脚本')
        notebook.add(commands, text='开源建模指令')
        self.code = scrolledtext.ScrolledText(script, font=('Consolas', 11), height=12)
        self.code.pack(fill='both', expand=True)
        self.code.insert('1.0', '# 默认只读；不会保存或修改模型\nresult = snapshot()\n')
        row = ttk.Frame(script)
        row.pack(fill='x', pady=(10, 0))
        self.timeout = tk.IntVar(value=60)
        ttk.Label(row, text='超时秒数').pack(side='left')
        ttk.Entry(row, textvariable=self.timeout, width=6).pack(side='left', padx=8)
        button(row, '提交脚本', self.submit_script, True).pack(side='left')
        from blender_control import catalog
        self.entries = catalog()['tools']
        self.command = tk.StringVar(value='object_create')
        combo = ttk.Combobox(commands, textvariable=self.command, values=[e['name'] for e in self.entries], state='readonly')
        combo.pack(fill='x')
        self.description = scrolledtext.ScrolledText(commands, height=9, font=('Consolas', 9))
        self.description.pack(fill='both', expand=True, pady=8)
        ttk.Label(commands, text='参数 JSON（单位和参数以当前指令说明为准）').pack(anchor='w')
        self.arguments = scrolledtext.ScrolledText(commands, height=5, font=('Consolas', 10))
        self.arguments.pack(fill='x', pady=8)
        self.arguments.insert('1.0', '{"type":"cube","name":"RemoteB_Cube"}')
        combo.bind('<<ComboboxSelected>>', self.show_schema)
        self.show_schema()
        button(commands, '提交指令', self.submit_command, True).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.image = tk.StringVar(value='preview.png')
        ttk.Entry(row, textvariable=self.image, width=25).pack(side='left', padx=(0, 8))
        button(row, '获取输出图像', lambda: self.send({'action': 'image', 'file': self.image.get()})).pack(side='left')
        button(row, '安装 Blender 技能', self.install_skill).pack(side='left', padx=8)
        ttk.Label(frame, text='任务 ID、结果及 traceback 在主窗口日志页。超时后先检查暂停和迟到结果，不自动重试。', wraplength=850).pack(anchor='w', pady=(10, 0))

    def show_schema(self, event=None):
        from blender_control import catalog
        self.description.delete('1.0', 'end')
        self.description.insert('1.0', json.dumps(catalog(self.command.get())['tools'][0], ensure_ascii=False, indent=2))

    def send(self, params):
        from tkinter import messagebox
        try:
            validate_blender_request(params)
        except (ValueError, TypeError) as exc:
            messagebox.showerror('未提交', str(exc), parent=self.window)
            return
        self.owner.call('submitted', lambda c: c.request('POST', '/api/jobs', {'operation': 'blender_control', 'params': params}))

    def submit_script(self):
        self.send({'action': 'script', 'code': self.code.get('1.0', 'end-1c'), 'timeout_seconds': self.timeout.get()})

    def submit_command(self):
        from tkinter import messagebox
        try:
            arguments = json.loads(self.arguments.get('1.0', 'end-1c'))
        except ValueError as exc:
            messagebox.showerror('参数 JSON 无效', str(exc), parent=self.window)
            return
        self.send({'action': 'tool', 'name': self.command.get(), 'arguments': arguments, 'timeout_seconds': 60})

    def install_skill(self):
        from cad_skills import install_project_skills
        from tkinter import messagebox
        try:
            result = install_project_skills(self.owner.variables['workspace'].get(), names=('remote-b-blender',))
            self.owner.queue.put(('message', json.dumps(result, ensure_ascii=False)))
        except Exception as exc:
            messagebox.showerror('技能未安装', str(exc), parent=self.window)
