"""Three-page B desktop layout; existing launcher methods own all actions."""
import os
import queue
import tkinter as tk
from tkinter import ttk
from desktop_ui import DesktopShell,StatusCard,LogView,section,button


def build_launcher(app,version):
    app.root.title('Remote B Hub · B 端工作站')
    shell=app.shell=DesktopShell(app.root,'b','工作站概览','管理任务代理与 SolidWorks，查看当前运行状态。')
    app.status=shell.footer
    app.health_results=queue.Queue()
    home=shell.home
    cards=ttk.Frame(home)
    cards.pack(fill='x',pady=(0,20))
    for column in range(3):cards.columnconfigure(column,weight=1,uniform='cards')
    app.agent_card=StatusCard(cards,0,'任务代理','未启动','等待启动本机任务代理')
    app.sw_card=StatusCard(cards,1,'SOLIDWORKS','待检查','检查当前登录会话的 COM')
    app.nas_card=StatusCard(cards,2,'NAS 服务','待检查','尚未验证连接状态')
    actions=section(home,'启动与控制','代理启动后接收 A 端任务；停止时会等待当前任务完成。')
    for column in range(3):actions.columnconfigure(column,weight=1)
    for index,(label,callback,primary,icon) in enumerate([
        ('启动任务代理',app.start,True,'play'),('启动 SolidWorks',app.start_sw,False,'computer'),
        ('检查运行状态',app.check,False,'refresh'),('停止任务代理',app.stop,False,'stop'),
        ('解除 CAD 暂停',app.clear_script_pause,False,'check'),('最小化驻留',app.root.iconify,False,'computer')]):
        button(actions,label,callback,primary,icon).grid(row=index//3,column=index%3,sticky='ew',padx=(0,10) if index%3<2 else 0,pady=(0,10))
    detail=section(home,'当前运行详情')
    app.runtime_detail=tk.StringVar(value='代理未运行。配置完成后，可从上方启动。')
    ttk.Label(detail,textvariable=app.runtime_detail,style='Card.TLabel',wraplength=730).pack(anchor='w')
    app.job_detail=tk.StringVar(value='当前任务：无')
    ttk.Label(detail,textvariable=app.job_detail,style='CardMuted.TLabel',wraplength=730).pack(anchor='w',pady=(9,0))
    shortcut=ttk.Frame(home)
    shortcut.pack(fill='x',pady=(0,12))
    button(shortcut,'查看日志',lambda:shell.show('logs'),'','logs').pack(side='left',padx=(0,10))
    button(shortcut,'连接与路径设置',lambda:shell.show('settings'),icon='settings').pack(side='left')
    ttk.Label(home,text='关闭窗口会退出启动器，并等待代理完成当前任务；需要后台运行时请选择“最小化驻留”。',
              style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(10,0))
    app.log_view=LogView(shell.pages['logs'],app.directory)
    app.log_widget=app.log_view.widget
    fields=section(shell.settings,'连接与建模路径','修改设置前，请先停止代理并等待当前任务完成。')
    fields.columnconfigure(1,weight=1)
    app.variables={}
    labels=[('server_url','NAS 服务地址',None),('token','B Token',None),
        ('output_dir','CAD 输出目录','directory'),('part_template','零件模板 (.prtdot)','file'),
        ('assembly_template','装配模板 (.asmdot)','file'),('sw_exe','SolidWorks 程序','file'),
        ('interop_dir','Interop 目录','directory')]
    for row,(key,label,browse) in enumerate(labels):
        ttk.Label(fields,text=label,style='Card.TLabel').grid(row=row,column=0,sticky='w',padx=(0,18),pady=8)
        app.variables[key]=tk.StringVar(value=app.config[key])
        ttk.Entry(fields,textvariable=app.variables[key],show='●' if key=='token' else '').grid(row=row,column=1,sticky='ew',pady=8)
        if browse:button(fields,'浏览',lambda k=key,b=browse:app.browse(k,b)).grid(row=row,column=2,padx=(8,0))
    ttk.Label(fields,text='Interop 留空时自动定位。Token 使用当前 Windows 用户加密保存。',style='CardMuted.TLabel',wraplength=650).grid(row=len(labels),column=0,columnspan=3,sticky='w',pady=(8,0))
    options=section(shell.settings,'运行偏好')
    for key,label in [('auto_start_sw','CAD 任务到达时自动启动 SolidWorks'),('auto_start_agent','打开应用时自动启动任务代理'),
        ('auto_restart_agent','代理意外退出后自动重启'),('start_at_login','Windows 登录后自动驻留')]:
        app.variables[key]=tk.BooleanVar(value=app.config[key])
        ttk.Checkbutton(options,text=label,variable=app.variables[key]).pack(anchor='w')
    permissions=section(shell.settings,'远端控制与截图','仅向可信任的 A 端开放脚本操作；完整权限脚本不是沙箱。')
    for key,label in [('allow_sw_scripts','允许 A 执行完整权限 SW Python 脚本及安全恢复'),
        ('screenshots_enabled','允许上传 SolidWorks 窗口截图'),('capture_on_error','CAD 任务失败时自动截图')]:
        app.variables[key]=tk.BooleanVar(value=app.config[key])
        ttk.Checkbutton(permissions,text=label,variable=app.variables[key]).pack(anchor='w')
    controls=ttk.Frame(shell.settings)
    controls.pack(fill='x',pady=(0,18))
    button(controls,'保存设置',app.save,True,'check').pack(side='left',padx=(0,10))
    button(controls,'检查更新',app.open_update,icon='refresh').pack(side='left',padx=(0,10))
    button(controls,'打开日志目录',lambda:os.startfile(str(app.directory)),icon='folder').pack(side='left')
    ttk.Label(shell.settings,text='执行器 '+version['executor_sha256'][:12]+'  ·  '+version.get('release_tag','本地源码版本'),
              style='Muted.TLabel').pack(anchor='w',pady=(0,10))
