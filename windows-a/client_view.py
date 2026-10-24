"""Three-page A desktop layout; actions use the existing authenticated client."""
import os
import tkinter as tk
from tkinter import ttk
from desktop_ui import DesktopShell,StatusCard,LogView,section,button


def build_client(app):
    app.root.title('Remote B Hub · A 端控制台')
    shell=app.shell=DesktopShell(app.root,'a','首页','A 端控制台')
    home=shell.home
    cards=ttk.Frame(home)
    cards.pack(fill='x',pady=(0,16))
    for column in range(3):cards.columnconfigure(column,weight=1,uniform='cards')
    app.connection_card=StatusCard(cards,0,'电脑 B','待检查','尚未取得代理在线状态')
    app.sw_card=StatusCard(cards,1,'SOLIDWORKS','待检查','通过实际任务确认连接')
    app.task_card=StatusCard(cards,2,'最近任务','暂无任务','提交后显示任务状态')
    actions=ttk.Frame(home)
    actions.pack(fill='x',pady=(0,10))
    for column in range(3):actions.columnconfigure(column,weight=1)
    for index,(label,callback,primary,icon) in enumerate([
        ('启动 Codex',app.start_codex,True,'play'),('CAD 管理',app.open_cad_control,False,'computer'),
        ('建模技能',app.open_skills,False,'settings'),('SW 脚本',app.open_script,False,'logs'),
        ('检查 B 在线',app.refresh_status,False,'refresh'),
        ('Blender 控制',app.open_blender,False,'computer')]):
        button(actions,label,callback,primary,icon).grid(row=index//3,column=index%3,sticky='ew',padx=(0,10) if index%3<2 else 0,pady=(0,10))
    current=section(home,'当前任务')
    ttk.Entry(current,textvariable=app.job_id,state='readonly').pack(fill='x')
    row=ttk.Frame(current,style='Card.TFrame')
    row.pack(fill='x',pady=(12,0))
    button(row,'读取任务结果',app.read_job,icon='refresh').pack(side='left',padx=(0,10))
    button(row,'查看详细日志',lambda:shell.show('logs'),icon='logs').pack(side='left')
    button(row,'SW 截图',lambda:app.call('submitted',lambda c:c.request('POST','/api/jobs',{'operation':'screenshot'})),icon='computer').pack(side='left',padx=10)

    logs=shell.pages['logs']
    row=ttk.Frame(logs)
    row.pack(fill='x',pady=(0,10))
    ttk.Label(row,text='任务 ID').pack(side='left',padx=(0,10))
    ttk.Entry(row,textvariable=app.job_id).pack(side='left',fill='x',expand=True,padx=(0,8))
    button(row,'读取任务',app.read_job).pack(side='left',padx=(0,6))
    button(row,'列出截图',app.list_images).pack(side='left')
    row=ttk.Frame(logs)
    row.pack(fill='x',pady=(0,14))
    ttk.Label(row,text='截图附件').pack(side='left',padx=(0,10))
    app.artifacts=ttk.Combobox(row,textvariable=app.artifact_id,state='readonly')
    app.artifacts.pack(side='left',fill='x',expand=True,padx=(0,8))
    button(row,'下载并查看',app.open_image).pack(side='left')
    app.log_view=LogView(logs,app.directory)
    app.output=app.log_view.widget
    fields=section(shell.settings,'连接设置','保存一次后，pc-b MCP 可读取当前用户已加密的连接配置。')
    fields.columnconfigure(1,weight=1)
    for row,(key,label) in enumerate([('server_url','NAS 服务入口'),('token','A Token'),('workspace','A 仓库工作目录')]):
        ttk.Label(fields,text=label,style='Card.TLabel').grid(row=row,column=0,sticky='w',padx=(0,18),pady=9)
        ttk.Entry(fields,textvariable=app.variables[key],show='●' if key=='token' else '').grid(row=row,column=1,sticky='ew',pady=9)
    def browse():
        from tkinter import filedialog
        path=filedialog.askdirectory(parent=app.root,title='选择 A 仓库目录')
        if path:app.variables['workspace'].set(path)
    button(fields,'浏览',browse).grid(row=2,column=2,padx=(8,0))
    ttk.Label(fields,text='A Token 对应 NAS 的 HUB_A_TOKEN；请使用 A 端凭据。',style='CardMuted.TLabel').grid(row=3,column=0,columnspan=3,sticky='w',pady=(10,0))
    controls=ttk.Frame(shell.settings)
    controls.pack(fill='x',pady=(0,20))
    button(controls,'保存设置',app.save,True,'check').pack(side='left',padx=(0,10))
    button(controls,'检查更新',app.open_update,icon='refresh').pack(side='left',padx=(0,10))
    button(controls,'打开日志目录',lambda:os.startfile(str(app.directory)),icon='folder').pack(side='left')
    about=section(shell.settings,'关于连接与控制')
    ttk.Label(about,text='SolidWorks 2023 / Blender · 通过 pc-b 连接 B\n\n两套程序的脚本和图像权限分别由 B 端控制。UU 等实时远控需单独配置。',
              style='CardMuted.TLabel',wraplength=700,justify='left').pack(anchor='w')
    shell.footer.set('准备就绪 · 运行详情见日志页')
