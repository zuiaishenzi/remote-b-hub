"""Shared native Tk desktop shell. UI only; no credentials, network or CAD operations."""
from collections import deque
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext

BG='#f3f5fa'
INK='#18243a'
MUTED='#68758b'
LINE='#e2e7f0'
BLUE='#4263e8'
NAV='#152239'


def asset(name):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    return root/'assets'/name


def install_theme(root, product):
    style=ttk.Style(root)
    style.theme_use('clam')
    root.configure(bg=BG)
    root.option_add('*Font',('Microsoft YaHei UI',10))
    style.configure('.',font=('Microsoft YaHei UI',10),foreground=INK,background=BG)
    style.configure('TFrame',background=BG)
    style.configure('Card.TFrame',background='white')
    style.configure('TLabel',background=BG,foreground=INK)
    style.configure('Muted.TLabel',foreground=MUTED)
    style.configure('Card.TLabel',background='white')
    style.configure('CardMuted.TLabel',background='white',foreground=MUTED)
    style.configure('TButton',padding=(14,9),background='white',bordercolor=LINE,lightcolor='white',darkcolor='white',relief='flat')
    style.map('TButton',background=[('active','#edf1fe'),('pressed','#e2e8ff')],bordercolor=[('focus',BLUE)])
    style.configure('Primary.TButton',foreground='white',background=BLUE,bordercolor=BLUE,lightcolor=BLUE,darkcolor=BLUE)
    style.map('Primary.TButton',background=[('active','#3452d3'),('pressed','#2944bc')],foreground=[('disabled','#ccd5ff')])
    style.configure('TEntry',padding=8,fieldbackground='white',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.map('TEntry',bordercolor=[('focus',BLUE)])
    style.configure('TCombobox',padding=7,fieldbackground='white',bordercolor=LINE)
    style.map('TCombobox',fieldbackground=[('readonly','white')],foreground=[('readonly',INK)])
    style.configure('TCheckbutton',background='white',padding=(0,5))
    style.map('TCheckbutton',background=[('active','white')])
    style.configure('TScrollbar',background='#c8d0df',troughcolor=BG,borderwidth=0,arrowsize=12)
    name='RemoteBClient' if product=='a' else 'RemoteBHub'
    from PIL import Image, ImageTk
    with Image.open(asset(name+'.png')) as icon:
        root._app_icon=ImageTk.PhotoImage(icon.copy(),master=root)
    root.iconphoto(True,root._app_icon)
    if sys.platform=='win32':
        root.iconbitmap(str(asset(name+'.ico')))


def symbol(master,name,color=BLUE,size=20):
    from PIL import Image,ImageDraw,ImageTk
    s=4
    image=Image.new('RGBA',(size*s,size*s))
    draw=ImageDraw.Draw(image)
    def points(values):return [(round(x*size*s/24),round(y*size*s/24)) for x,y in values]
    def line(values):draw.line(points(values),fill=color,width=max(2,round(size*s/12)),joint='curve')
    if name=='home':
        line([(3,11),(12,3),(21,11)]);line([(6,10),(6,21),(18,21),(18,10)]);line([(10,21),(10,15),(14,15),(14,21)])
    elif name=='logs':
        line([(6,3),(18,3),(18,21),(6,21),(6,3)])
        for y in (8,12,16):line([(9,y),(15,y)])
    elif name=='settings':
        for y,x in [(6,8),(12,16),(18,10)]:
            line([(3,y),(21,y)]);draw.ellipse([*points([(x-2,y-2),(x+2,y+2)])[0],*points([(x-2,y-2),(x+2,y+2)])[1]],fill=NAV,outline=color,width=2*s)
    elif name=='play':draw.polygon(points([(7,4),(20,12),(7,20)]),fill=color)
    elif name=='stop':draw.rounded_rectangle((*points([(5,5)])[0],*points([(19,19)])[0]),radius=3*s,fill=color)
    elif name=='refresh':
        draw.arc((*points([(4,4)])[0],*points([(20,20)])[0]),30,310,fill=color,width=2*s);line([(19,3),(20,9),(14,8)])
    elif name=='computer':
        line([(3,4),(21,4),(21,17),(3,17),(3,4)]);line([(12,17),(12,21)]);line([(8,21),(16,21)])
    elif name=='folder':line([(3,7),(3,20),(21,20),(21,8),(11,8),(9,4),(3,4),(3,7)])
    elif name=='check':line([(4,12),(10,18),(21,6)])
    else:line([(4,12),(20,12)]);line([(12,4),(12,20)])
    image=image.resize((size,size),Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image,master=master)


def button(parent,text,command,primary=False,icon=None):
    item=ttk.Button(parent,text=text,command=command,style='Primary.TButton' if primary else 'TButton')
    if icon:
        item._icon=symbol(parent,icon,'white' if primary else BLUE,17)
        item.configure(image=item._icon,compound='left')
    return item


def section(parent,title,subtitle=None):
    border=tk.Frame(parent,bg='white',highlightbackground=LINE,highlightthickness=1,bd=0)
    border.pack(fill='x',pady=(0,16))
    inner=ttk.Frame(border,style='Card.TFrame',padding=18)
    inner.pack(fill='both',expand=True)
    ttk.Label(inner,text=title,style='Card.TLabel',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w')
    if subtitle:ttk.Label(inner,text=subtitle,style='CardMuted.TLabel',wraplength=690).pack(anchor='w',pady=(4,0))
    body=ttk.Frame(inner,style='Card.TFrame')
    body.pack(fill='both',expand=True,pady=(14,0))
    return body


class StatusCard:
    def __init__(self,parent,column,title,value='待检查',detail='尚未获取运行状态'):
        border=tk.Frame(parent,bg='white',highlightbackground=LINE,highlightthickness=1,bd=0)
        border.grid(row=0,column=column,sticky='nsew',padx=(0,12) if column<2 else 0)
        body=ttk.Frame(border,style='Card.TFrame',padding=(18,16))
        body.pack(fill='both',expand=True)
        ttk.Label(body,text=title,style='CardMuted.TLabel').pack(anchor='w')
        self.value=ttk.Label(body,text=value,style='Card.TLabel',font=('Microsoft YaHei UI',17,'bold'))
        self.value.pack(anchor='w',pady=(8,7))
        self.detail=ttk.Label(body,text=detail,style='CardMuted.TLabel',wraplength=205)
        self.detail.pack(anchor='w')
        border.bind('<Configure>',lambda e:self.detail.configure(wraplength=max(120,e.width-38)))
    def set(self,value,detail,tone='neutral'):
        self.value.configure(text=value,foreground={'good':'#087b64','bad':'#b42335','busy':BLUE,'warn':'#a26813'}.get(tone,INK))
        self.detail.configure(text=detail)


class ScrollPage(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,bg=BG,bd=0,highlightthickness=0)
        bar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.body=ttk.Frame(self.canvas,padding=(0,0,12,16))
        self.window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window,width=e.width))
        self.bind_all('<MouseWheel>',self.wheel,add='+')
    def wheel(self,event):
        if self.winfo_ismapped() and event.widget.winfo_toplevel()==self.winfo_toplevel() and event.delta:
            steps=max(1,round(abs(event.delta)/120))
            self.canvas.yview_scroll(-steps if event.delta>0 else steps,'units')
            return 'break'


class DesktopShell:
    def __init__(self,root,product,title,subtitle):
        install_theme(root,product)
        width=max(940,min(1160,root.winfo_screenwidth()-80))
        height=max(620,min(840,root.winfo_screenheight()-90))
        left=max(0,(root.winfo_screenwidth()-width)//2)
        top=max(0,(root.winfo_screenheight()-height)//2-10)
        root.geometry(f'{width}x{height}+{left}+{top}')
        root.minsize(min(960,width),min(640,height))
        self.root,self.product=root,product
        self.sidebar=tk.Frame(root,bg=NAV,width=220)
        self.sidebar.pack(side='left',fill='y')
        self.sidebar.pack_propagate(False)
        from PIL import Image,ImageTk
        with Image.open(asset(('RemoteBClient' if product=='a' else 'RemoteBHub')+'.png')) as image:
            self.brand=ImageTk.PhotoImage(image.resize((40,40),Image.Resampling.LANCZOS),master=root)
        brand=tk.Frame(self.sidebar,bg=NAV)
        brand.pack(fill='x',padx=22,pady=(30,34))
        tk.Label(brand,image=self.brand,bg=NAV).pack(side='left')
        labels=tk.Frame(brand,bg=NAV)
        labels.pack(side='left',padx=(10,0))
        tk.Label(labels,text='REMOTE B',font=('Segoe UI',13,'bold'),fg='white',bg=NAV).pack(anchor='w')
        tk.Label(labels,text='A 端控制台' if product=='a' else 'B 端工作站',font=('Microsoft YaHei UI',9),fg='#9aaac4',bg=NAV).pack(anchor='w',pady=(2,0))
        self.nav={}
        self.nav_icons={}
        for key,label,icon in [('home','首页','home'),('logs','日志','logs'),('settings','设置','settings')]:
            frame=tk.Frame(self.sidebar,bg=NAV)
            frame.pack(fill='x',padx=14,pady=4)
            self.nav_icons[key]=(symbol(root,icon,'#aebed6'),symbol(root,icon,'white'))
            item=tk.Button(frame,text='   '+label,image=self.nav_icons[key][0],compound='left',
                anchor='w',padx=18,pady=13,bd=0,relief='flat',bg=NAV,fg='#b5c3d8',
                activebackground='#283b59',activeforeground='white',cursor='hand2',
                font=('Microsoft YaHei UI',11),command=lambda k=key:self.show(k))
            item.pack(fill='x')
            self.nav[key]=item
        bottom=tk.Frame(self.sidebar,bg=NAV)
        bottom.pack(side='bottom',fill='x',padx=24,pady=26)
        tk.Label(bottom,text='●  SOLIDWORKS 2023',fg='#93a9c7',bg=NAV,font=('Segoe UI',9)).pack(anchor='w')
        tk.Label(bottom,text='连接 · 执行 · 验证',fg='#7188aa',bg=NAV,font=('Microsoft YaHei UI',9)).pack(anchor='w',pady=(6,0))
        main=ttk.Frame(root,padding=(28,25,24,16))
        main.pack(side='left',fill='both',expand=True)
        self.heading=tk.StringVar(value=title)
        self.subtitle=tk.StringVar(value=subtitle)
        ttk.Label(main,textvariable=self.heading,font=('Microsoft YaHei UI',23,'bold')).pack(anchor='w')
        ttk.Label(main,textvariable=self.subtitle,style='Muted.TLabel').pack(anchor='w',pady=(5,20))
        self.container=ttk.Frame(main)
        self.container.pack(fill='both',expand=True)
        self.home_scroll=ScrollPage(self.container)
        self.home=self.home_scroll.body
        self.pages={'home':self.home_scroll,'logs':ttk.Frame(self.container)}
        self.scroll=ScrollPage(self.container)
        self.pages['settings']=self.scroll
        self.settings=self.scroll.body
        self.footer=tk.StringVar(value='准备就绪')
        ttk.Label(main,textvariable=self.footer,style='Muted.TLabel',wraplength=860).pack(anchor='w',pady=(12,0))
        self.titles={'home':(title,subtitle),'logs':('运行日志','查看任务结果、诊断信息与应用事件。'),
                     'settings':('设置','连接、路径与运行偏好，集中在这里管理。')}
        self.show('home')
    def show(self,key):
        if key not in self.pages:raise ValueError('Unknown desktop page')
        for name,page in self.pages.items():
            page.pack_forget()
            selected=name==key
            self.nav[name].configure(bg='#2a4167' if selected else NAV,fg='white' if selected else '#b5c3d8',image=self.nav_icons[name][int(selected)])
        self.pages[key].pack(fill='both',expand=True)
        self.heading.set(self.titles[key][0]);self.subtitle.set(self.titles[key][1])
        self.current=key


class LogView:
    def __init__(self,parent,directory):
        self.directory=Path(directory)
        self.lines=deque(maxlen=2000)
        tools=ttk.Frame(parent)
        tools.pack(fill='x',pady=(0,12))
        ttk.Label(tools,text='搜索日志').pack(side='left',padx=(0,8))
        self.query=tk.StringVar()
        entry=ttk.Entry(tools,textvariable=self.query)
        entry.pack(side='left',fill='x',expand=True,padx=(0,10))
        self.follow=tk.BooleanVar(value=True)
        ttk.Checkbutton(tools,text='自动滚动',variable=self.follow).pack(side='left',padx=6)
        button(tools,'导出',self.export).pack(side='left',padx=4)
        button(tools,'清空显示',self.clear).pack(side='left',padx=4)
        self.widget=scrolledtext.ScrolledText(parent,state='disabled',font=('Consolas',10),wrap='word',
            bg='#ffffff',fg=INK,insertbackground=BLUE,relief='flat',borderwidth=0,
            highlightthickness=1,highlightbackground=LINE,padx=16,pady=14)
        self.widget.pack(fill='both',expand=True)
        self.widget.tag_configure('error',foreground='#b42335')
        self.query.trace_add('write',lambda *args:self.render())
        ttk.Label(parent,text='搜索关键字以筛选显示；清空显示不会删除磁盘日志。',style='Muted.TLabel').pack(anchor='w',pady=(8,0))
    def append(self,text):
        self.lines.extend(str(text).splitlines(keepends=True))
        self.render()
    def render(self):
        query=self.query.get().casefold()
        position=self.widget.yview()[0]
        self.widget.configure(state='normal')
        self.widget.delete('1.0','end')
        for line in self.lines:
            if query and query not in line.casefold():continue
            tags=('error',) if any(word in line for word in ('失败','Traceback','ERROR','拒绝')) else ()
            self.widget.insert('end',line if line.endswith('\n') else line+'\n',tags)
        if self.follow.get():self.widget.see('end')
        else:self.widget.yview_moveto(position)
        self.widget.configure(state='disabled')
    def clear(self):
        self.lines.clear();self.render()
    def export(self):
        from tkinter import filedialog
        path=filedialog.asksaveasfilename(parent=self.widget.winfo_toplevel(),title='导出当前日志',
            defaultextension='.txt',initialfile='RemoteBHub-log.txt',filetypes=[('文本文件','*.txt')])
        if path:Path(path).write_text(''.join(self.lines),encoding='utf-8')


def append_event_log(path,text):
    path=Path(path)
    if path.exists() and path.stat().st_size>2_000_000:
        path.replace(path.with_suffix('.previous.log'))
    with path.open('a',encoding='utf-8') as stream:stream.write(text)
