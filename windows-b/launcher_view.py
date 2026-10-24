"""Three-page B desktop layout; existing launcher methods own all actions."""
import os
import queue
import tkinter as tk
from tkinter import ttk
from desktop_ui import DesktopShell,StatusCard,LogView,section,button,toggle_row,symbol


def build_launcher(app,version):
    app.root.title('Remote B Hub · B 端工作站')
    shell=app.shell=DesktopShell(app.root,'b','首页','B 端工作站')
    app.status=shell.footer
    app.health_results=queue.Queue()
    home=shell.home
    cards=ttk.Frame(home)
    cards.pack(fill='x',pady=(0,16))
    for column in range(3):cards.columnconfigure(column,weight=1,uniform='cards')
    app.agent_card=StatusCard(cards,0,'任务代理','未启动','等待启动本机任务代理')
    app.sw_card=StatusCard(cards,1,'SOLIDWORKS','待检查','检查当前登录会话的 COM')
    app.nas_card=StatusCard(cards,2,'NAS 服务','待检查','尚未验证连接状态')
    actions=ttk.Frame(home)
    actions.pack(fill='x',pady=(0,16))
    for column in range(3):actions.columnconfigure(column,weight=1)
    app.agent_icons={'start':symbol(app.root,'play','white',17),'stop':symbol(app.root,'stop','#b42335',17)}
    app.agent_toggle=button(actions,'启动任务代理',app.toggle_agent,True)
    app.agent_toggle.configure(image=app.agent_icons['start'],compound='left')
    app.agent_toggle.grid(row=0,column=0,sticky='ew',padx=(0,10))
    button(actions,'启动 SolidWorks',app.start_sw,icon='computer').grid(row=0,column=1,sticky='ew',padx=(0,10))
    button(actions,'刷新状态',app.check,icon='refresh').grid(row=0,column=2,sticky='ew')
    detail=section(home,'当前任务')
    app.runtime_detail=tk.StringVar(value='代理未运行')
    ttk.Label(detail,textvariable=app.runtime_detail,style='Card.TLabel',wraplength=640).pack(anchor='w')
    app.job_detail=tk.StringVar(value='任务 ID：无')
    ttk.Label(detail,textvariable=app.job_detail,style='CardMuted.TLabel',wraplength=640).pack(anchor='w',pady=(7,0))
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
        toggle_row(options,label,app.variables[key])
    permissions=section(shell.settings,'远端控制与截图','仅向可信任的 A 端开放脚本操作；完整权限脚本不是沙箱。')
    for key,label in [('allow_sw_scripts','允许 A 执行完整权限 SW Python 脚本及安全恢复'),
        ('screenshots_enabled','允许上传 SolidWorks 窗口截图'),('capture_on_error','CAD 任务失败时自动截图')]:
        app.variables[key]=tk.BooleanVar(value=app.config[key])
        toggle_row(permissions,label,app.variables[key])
    recovery=section(shell.settings,'CAD 恢复')
    button(recovery,'核对状态并解除暂停',app.clear_script_pause,icon='check').pack(anchor='w')
    controls=ttk.Frame(shell.settings)
    controls.pack(fill='x',pady=(0,18))
    button(controls,'保存设置',app.save,True,'check').pack(side='left',padx=(0,10))
    button(controls,'检查更新',app.open_update,icon='refresh').pack(side='left',padx=(0,10))
    button(controls,'打开日志目录',lambda:os.startfile(str(app.directory)),icon='folder').pack(side='left')
    ttk.Label(shell.settings,text='执行器 '+version['executor_sha256'][:12]+'  ·  '+version.get('release_tag','本地源码版本'),
              style='Muted.TLabel').pack(anchor='w',pady=(0,10))
