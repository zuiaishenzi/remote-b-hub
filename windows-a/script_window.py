"""Reviewable script editor; uses the same authenticated job API as MCP."""
from script_schema import validate_script_request


class ScriptWindow:
    def __init__(self, owner):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title('SW2023 远端 Python COM 脚本')
        self.window.geometry('900x650')
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='完整用户权限，非沙箱。先读取状态，再分步修改；脚本不会自动保存。').pack(anchor='w')
        ttk.Label(panel, text='可用：sw、model、read(obj, member)、snapshot()、log()、output_dir、part_template、assembly_template').pack(anchor='w')
        self.code = scrolledtext.ScrolledText(panel, font=('Consolas', 11))
        self.code.pack(fill='both', expand=True, pady=10)
        self.code.insert('1.0', '# 默认示例只读，不修改模型\nresult = snapshot()\nlog("active document inspected")\n')
        self.timeout = tk.IntVar(value=60)
        row = ttk.Frame(panel)
        row.pack(fill='x')
        ttk.Label(row, text='超时秒数（10–300）').pack(side='left')
        ttk.Entry(row, textvariable=self.timeout, width=6).pack(side='left', padx=6)
        ttk.Button(row, text='读取 SW 当前状态', command=self.inspect).pack(side='left', padx=6)
        ttk.Button(row, text='提交脚本', command=self.submit).pack(side='left', padx=6)
        ttk.Label(panel, text='任务 ID 和结果显示在主窗口；点击“读取任务/错误”查看。失败不自动重试。').pack(anchor='w', pady=8)

    def inspect(self):
        self.owner.call('submitted', lambda c: c.request('POST', '/api/jobs',
                       {'operation': 'sw_script', 'params': {'mode': 'inspect'}}))

    def submit(self):
        from tkinter import messagebox
        try:
            params = {'mode': 'execute', 'code': self.code.get('1.0', 'end-1c'),
                      'timeout_seconds': self.timeout.get()}
            validate_script_request(params)
        except Exception as exc:
            messagebox.showerror('脚本未提交', str(exc), parent=self.window)
            return
        self.owner.call('submitted', lambda c: c.request('POST', '/api/jobs',
                       {'operation': 'sw_script', 'params': params}))
