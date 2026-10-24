"""A desktop controls for authenticated, serialized CAD lifecycle jobs."""
import queue
import threading
import time


class CadControlWindow:
    def __init__(self, owner):
        import tkinter as tk
        from tkinter import ttk
        self.owner, self.messages = owner, queue.Queue()
        self.window = tk.Toplevel(owner.root)
        self.window.title('电脑 B · CAD 状态、启动与安全恢复')
        self.window.geometry('760x280')
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='恢复前查看错误和 SW 截图。旧脚本仍运行时不能解除；不强杀 SW，不重试失败任务。', wraplength=730).pack(anchor='w')
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=12)
        ttk.Button(row, text='读取暂停与进程状态', command=self.state).pack(side='left', padx=4)
        ttk.Button(row, text='启动/连接 SW', command=lambda: self.submit({'action':'start'})).pack(side='left', padx=4)
        self.pause_id = tk.StringVar()
        ttk.Label(panel, text='当前暂停 ID（读取状态后自动填写）').pack(anchor='w')
        ttk.Entry(panel, textvariable=self.pause_id).pack(fill='x', pady=5)
        self.acknowledge = tk.BooleanVar(value=False)
        from desktop_ui import ToggleControl,BG
        ToggleControl(panel,self.acknowledge,'已确认当前状态','尚未确认状态',background=BG).pack(anchor='w')
        ttk.Button(panel, text='安全解除本次暂停', command=self.resume).pack(anchor='w', pady=8)
        self.status = tk.StringVar(value='尚未读取状态；任务结果显示在 A 主窗口。')
        ttk.Label(panel, textvariable=self.status, wraplength=730).pack(anchor='w')
        self.window.after(200, self.tick)

    def submit(self, params):
        self.owner.call('submitted', lambda c: c.request('POST', '/api/jobs',
                        {'operation':'cad_control', 'params':params}))

    def state(self):
        # Resolve credentials on the UI thread; networking happens in a worker thread.
        try:
            client = self.owner.client()
        except Exception as exc:
            self.status.set(str(exc))
            return
        self.acknowledge.set(False)
        self.pause_id.set('')
        def run():
            try:
                task = client.request('POST', '/api/jobs', {'operation':'cad_control','params':{'action':'state'}})
                self.owner.queue.put(('submitted',task))
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    job = client.request('GET','/api/jobs/'+task['job_id'])
                    if job['status'] not in ('queued','running'):
                        self.owner.queue.put(('job',job))
                        if job['status']!='done':
                            raise RuntimeError('状态查询失败；请读取主窗口的诊断')
                        self.messages.put(job['result']['value'])
                        return
                    time.sleep(1)
                raise TimeoutError('状态查询仍未完成；请继续查询现有任务，不要重复提交')
            except Exception as exc:
                from desktop_config import redact
                self.messages.put({'error':redact(str(exc),client.token)})
        threading.Thread(target=run,daemon=True).start()

    def resume(self):
        from tkinter import messagebox
        from cad_control_schema import validate_cad_control
        params = {'action':'resume','pause_id':self.pause_id.get(),
                  'acknowledge_state':self.acknowledge.get()}
        try:
            validate_cad_control(params)
        except ValueError as exc:
            messagebox.showerror('未提交恢复',str(exc),parent=self.window)
            return
        self.submit(params)
        self.acknowledge.set(False)
        self.pause_id.set('')

    def tick(self):
        while not self.messages.empty():
            value = self.messages.get_nowait()
            self.pause_id.set(value.get('pause_id') or '')
            self.status.set(value.get('error') or (
                f"暂停={value['paused']}，旧脚本运行={value['helper_running']}，可恢复={value['can_resume']}；"
                + value.get('reason','')))
        self.window.after(200,self.tick)
