"""A-side reviewed modeling templates; all network results use the main log."""
import json
import uuid

from cad_skills import DEFAULTS, catalog, install_project_skills, plan_part, review_part


class SkillWindow:
    def __init__(self, owner):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title('SolidWorks 2023 — 建模技能')
        self.window.geometry('900x680')
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='毫米参数 → 严格配方 → B 端执行 → 真实任务复核').pack(anchor='w')
        self.template = tk.StringVar(value='cylinder')
        selector = ttk.Combobox(panel, textvariable=self.template, values=list(DEFAULTS), state='readonly')
        selector.pack(fill='x', pady=5)
        selector.bind('<<ComboboxSelected>>', self.reset)
        self.name = tk.StringVar()
        ttk.Entry(panel, textvariable=self.name).pack(fill='x', pady=5)
        self.parameters = scrolledtext.ScrolledText(panel, height=9)
        self.parameters.pack(fill='x')
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', pady=8)
        for label, action in (('生成并校验', self.plan), ('提交 B（创建新零件）', self.submit),
                              ('复核主窗口任务 ID', self.review), ('安装到工作目录', self.install)):
            ttk.Button(buttons, text=label, command=action).pack(side='left', padx=3)
        self.output = scrolledtext.ScrolledText(panel, wrap='word')
        self.output.pack(fill='both', expand=True)
        ttk.Label(panel, text='执行日志和任务 ID 显示在主窗口。体积为理论值；实际深度、孔贯通与拓扑另行检验。').pack(anchor='w')
        self.reset()
        self.show(catalog())

    def show(self, value):
        self.output.delete('1.0', 'end')
        self.output.insert('end', json.dumps(value, ensure_ascii=False, indent=2))

    def reset(self, event=None):
        self.parameters.delete('1.0', 'end')
        self.parameters.insert('end', json.dumps(DEFAULTS[self.template.get()], indent=2))
        self.name.set('Skill_' + self.template.get() + '_' + uuid.uuid4().hex[:10])

    def contract(self):
        return plan_part(self.template.get(), json.loads(self.parameters.get('1.0', 'end')), self.name.get())

    def guarded(self, action):
        from tkinter import messagebox
        try:
            return action()
        except Exception as exc:
            messagebox.showerror('建模技能', str(exc), parent=self.window)

    def plan(self):
        return self.guarded(lambda: self.show(self.contract()))

    def submit(self):
        def action():
            plan = self.contract()
            self.show(plan)
            if not plan['execution_ready']:
                raise ValueError('此模板未通过实机验收，已禁止自动提交。' + plan['validation'])
            def send(client):
                if client.request('GET', '/api/status').get('online') is not True:
                    raise RuntimeError('B 端离线，请先启动代理；未提交建模任务。')
                return client.request('POST', '/api/jobs', {'operation': 'sw_recipe',
                                      'params': {'recipe': plan['recipe']}})
            self.owner.call('submitted', send)
        return self.guarded(action)

    def review(self):
        def action():
            plan = self.contract()
            identity = str(uuid.UUID(self.owner.job_id.get()))
            self.owner.call('skill-review', lambda client: review_part(
                plan['template'], plan['parameters'], plan['name'],
                client.request('GET', '/api/jobs/' + identity)))
        return self.guarded(action)

    def install(self):
        return self.guarded(lambda: self.show(install_project_skills(self.owner.variables['workspace'].get())))
