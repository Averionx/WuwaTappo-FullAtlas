"""Per-installation update ownership and progress shared with the helper."""
from pathlib import Path
import json
import os
import time
import uuid
from desktop_assistant import atomic_json

TERMINAL = {'complete', 'failed'}


class UpdateLease:
    def __init__(self, root):
        self.path = Path(root)/'.updates/install.lock'
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(exist_ok=True)
        self.stream = self.path.open('a+b')
        self.stream.seek(0);self.stream.write(b'0');self.stream.flush();self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close();self.stream=None
            raise RuntimeError('已有更新任务正在运行，请等待完成。')
        return self

    def __exit__(self, *_):
        if self.stream:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close();self.stream=None


def write_progress(folder, phase, percent, message, **extra):
    folder=Path(folder)
    value={'phase':phase,'percent':round(max(0,min(100,percent)),1),'message':message,
           'updated_at':time.time(),'pid':os.getpid(),**extra}
    import psutil
    value['process_started']=psutil.Process(value['pid']).create_time()
    # The UI and the old host may briefly read this file during the handoff.
    # Windows can refuse rename while a reader is open; use a distinct temp
    # file per writer and retry without restarting the update transaction.
    temporary=folder/('progress.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        deadline=time.monotonic()+2
        while True:
            try:os.replace(temporary,folder/'progress.json');break
            except PermissionError:
                if time.monotonic()>=deadline:raise
                time.sleep(.01)
    finally:temporary.unlink(missing_ok=True)
    return value


def read_progress(root):
    try:
        updates=Path(root)/'.updates'
        pointer=json.loads((updates/'install-current.json').read_text(encoding='utf-8'))
        job=pointer['job']
        if not isinstance(job,str) or len(job)!=32 or any(c not in '0123456789abcdef' for c in job):return {}
        value=json.loads((updates/job/'progress.json').read_text(encoding='utf-8'))
        value.update(job=job,version=pointer['version'])
        result_file=updates/job/'result.json'
        if result_file.exists():
            result=json.loads(result_file.read_text(encoding='utf-8'))
            value.update(phase='complete' if result.get('ok') else 'failed',message='更新完成，新版本已启动。' if result.get('ok') else '更新失败：'+str(result.get('error','请重试')))
        if value['phase'] not in TERMINAL:
            import psutil
            try:
                alive=abs(psutil.Process(value['pid']).create_time()-value['process_started'])<.1
            except psutil.NoSuchProcess:alive=False
            except psutil.AccessDenied:alive=True
            if not alive:
                value.update(phase='failed',message='上次更新任务已中断，请重新更新。')
        return value
    except (OSError,ValueError,KeyError,TypeError):return {}


def progress_window(folder, *, preview=False):
    """Independent UI survives closure/replacement of the native pet EXE."""
    import tkinter as tk
    import sys
    folder=Path(folder)
    fonts=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]/'build'))/'ui_fonts'
    private_fonts=[]
    if os.name=='nt' and fonts.is_dir():
        import ctypes
        for font_path in fonts.glob('*.ttf'):
            if ctypes.windll.gdi32.AddFontResourceExW(str(font_path),0x10,None):private_fonts.append(font_path)
    app=tk.Tk();app.title('WuwaTappo全图鉴版 · 更新进度')
    background='#fff6e2';transparent='#010101';ink='#986b49';muted='#b0977c'
    app.configure(bg=transparent);app.overrideredirect(True);app.resizable(False,False)
    if os.name=='nt':app.attributes('-transparentcolor',transparent);app.attributes('-toolwindow',True)
    app.attributes('-topmost',True)
    family='WT Tappo UI' if private_fonts else 'Microsoft YaHei UI'
    def font(size,bold=False):return (family,-size,'bold' if bold else 'normal')
    width,height=500,560
    app.geometry(f'{width}x{height}+{(app.winfo_screenwidth()-width)//2}+{(app.winfo_screenheight()-height)//2}')
    app.protocol('WM_DELETE_WINDOW',lambda:None)
    def rounded(canvas,x1,y1,x2,y2,r,fill,outline=None,width=1):
        points=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return canvas.create_polygon(points,smooth=True,splinesteps=32,fill=fill,outline=outline or fill,width=width)
    shell=tk.Canvas(app,bg=transparent,highlightthickness=0,bd=0);shell.pack(fill='both',expand=True)
    rounded(shell,8,11,width-8,height-5,28,'#dcb78c')
    rounded(shell,8,8,width-8,height-8,28,background,'#e7c298',2)
    frame=tk.Frame(shell,bg=background);shell.create_window(34,32,window=frame,anchor='nw',width=width-68,height=height-66)
    frame.columnconfigure(0,weight=1);frame.rowconfigure(4,weight=1)
    tk.Label(frame,text='WUWA TAPPO · '+('本地样式预览' if preview else '版本更新'),bg=background,fg='#b28d66',font=font(11),anchor='w').grid(row=0,column=0,sticky='ew',pady=(0,6))
    title=tk.Label(frame,text='正在更新，请稍候',bg=background,fg='#9d653e',font=font(22,True),anchor='w');title.grid(row=1,column=0,sticky='ew',pady=(0,14))
    version_box=tk.Canvas(frame,height=42,bg=background,highlightthickness=0);version_box.grid(row=2,column=0,sticky='ew',pady=(0,12))
    try:
        pending=json.loads((folder/'pending.json').read_text(encoding='utf-8'))
        versions='当前 v'+str(pending.get('from_version','—'))+'  →  最新 v'+str(pending['version'])
    except (OSError,ValueError,KeyError):versions='正在安装已校验的版本更新'
    def draw_version(event):
        version_box.delete('all');rounded(version_box,1,1,event.width-1,41,14,'#f9e7ca','#efd2a8')
        version_box.create_text(14,21,text=versions,anchor='w',fill=ink,font=font(13))
    version_box.bind('<Configure>',draw_version)
    message=tk.Label(frame,text='升级包已准备好，正在自动安装并重启。',bg=background,fg=ink,font=font(13),wraplength=width-70,anchor='w',justify='left');message.grid(row=3,column=0,sticky='ew',pady=(0,12))
    card=tk.Canvas(frame,bg=background,highlightthickness=0);card.grid(row=4,column=0,sticky='nsew',pady=(0,10))
    details=tk.Frame(card,bg='#fffbed');details_id=card.create_window(14,12,window=details,anchor='nw')
    def resize_card(event):
        card.delete('card-background');shape=rounded(card,1,1,event.width-1,event.height-1,14,'#fffbed','#e9d0aa')
        card.itemconfigure(shape,tags='card-background');card.tag_lower(shape)
        card.itemconfigure(details_id,width=max(1,event.width-28),height=max(1,event.height-24))
    card.bind('<Configure>',resize_card)
    tk.Label(details,text='更新进度',bg='#fffbed',fg='#a16f47',font=font(13,True),anchor='w').pack(fill='x')
    phase_label=tk.Label(details,text='正在等待桌宠保存数据…',bg='#fffbed',fg='#a27a58',font=font(12),anchor='w');phase_label.pack(fill='x',pady=(5,6))
    bar=tk.Canvas(details,height=8,bg='#fffbed',highlightthickness=0);bar.pack(fill='x')
    percent=tk.Label(details,text='',bg='#fffbed',fg=muted,font=font(11),anchor='e');percent.pack(fill='x',pady=(4,6))
    stages=[]
    for text in ('下载升级包','校验与解压','备份并替换','启动新版本'):
        label=tk.Label(details,text='·  '+text,bg='#fffbed',fg=muted,font=font(12),anchor='w');label.pack(fill='x');stages.append((label,text))
    tk.Label(frame,text='账号、点数、装扮、开箱记录与设置均会保留。',bg=background,fg=muted,font=font(11),anchor='w').grid(row=5,column=0,sticky='ew',pady=(0,12))
    controls=tk.Frame(frame,bg=background,height=44);controls.grid(row=6,column=0,sticky='ew');controls.columnconfigure(0,weight=7);controls.columnconfigure(1,weight=5)
    def control(column,primary):
        canvas=tk.Canvas(controls,height=46,bg=background,highlightthickness=0,takefocus=True)
        canvas.grid(row=0,column=column,sticky='ew',padx=(0,6) if column==0 else (6,0))
        state={'text':'正在更新…' if primary else '请稍候','enabled':False,'action':None}
        def draw(_=None):
            canvas.delete('all');w=max(2,canvas.winfo_width())
            fill='#ffd394' if primary and state['enabled'] else '#ffe1ae' if primary else '#ffecd0'
            rounded(canvas,1,1,w-1,44,18,fill,'#e8b16f' if primary else '#e5be91')
            canvas.create_text(w/2,23,text=state['text'],fill='#97603b' if state['enabled'] else '#c2a17b',font=font(16 if primary else 13,primary))
            canvas.configure(cursor='hand2' if state['enabled'] else 'arrow')
        def act(_=None):
            if state['enabled'] and state['action']:state['action']()
        canvas.bind('<Configure>',draw);canvas.bind('<Button-1>',act);canvas.bind('<Return>',act)
        def change(text,enabled=False,action=None):state.update(text=text,enabled=enabled,action=action);draw()
        return change
    primary=control(0,True);secondary=control(1,False)
    if preview:
        secondary('关闭预览',True,app.destroy)
        app.bind('<Escape>',lambda _:app.destroy())
    def exit_application():
        if not preview:
            try:
                import urllib.request
                config=json.loads((folder.parent.parent/'local_config.json').read_text(encoding='utf-8-sig'))
                request=urllib.request.Request('http://127.0.0.1:'+str(int(config['port']))+'/assistant/quit',data=b'{}',headers={'Content-Type':'application/json','X-Local-Token':config['token']})
                with urllib.request.urlopen(request,timeout=2):pass
            except (OSError,ValueError,KeyError):pass
        app.destroy()
    done=False
    last_percent=0
    def refresh():
        nonlocal done,last_percent
        try:
            state=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
            result_file=folder/'result.json'
            if result_file.exists():
                result=json.loads(result_file.read_text(encoding='utf-8'))
                state.update(phase='complete' if result.get('ok') else 'failed',percent=100 if result.get('ok') else state['percent'],message='更新完成，新版本已启动。' if result.get('ok') else '更新失败：'+str(result.get('error','请重试')))
            phase=state['phase'];last_percent=max(0,min(100,float(state['percent'])))
            bar.delete('all');w=max(1,bar.winfo_width());rounded(bar,0,0,w,7,3,'#eeddbf')
            if last_percent>0:rounded(bar,0,0,max(6,w*last_percent/100),7,3,'#d6a263')
            percent.config(text=f'总进度 {last_percent:g}%')
            phase_label.config(text='等待返回软件重试' if phase=='failed' else state['message'])
            for (label,text),threshold in zip(stages,(60,75,96,100)):
                label.config(text=('✓  ' if last_percent>=threshold else '·  ')+text,fg=ink if last_percent>=threshold else muted)
            message.config(text='正在下载升级包，完成后会自动安装。' if phase=='downloading' else '升级包已准备好，正在自动安装并重启。')
            if state['phase']=='complete':
                title.config(text='更新完成');message.config(text='新版本已启动，可以继续使用桌宠。');primary('更新完成',True,app.destroy);secondary('关闭',True,app.destroy)
                if not done:done=True;app.after(1200,app.destroy)
                return
            if state['phase']=='failed':
                title.config(text='更新未完成');message.config(text='原程序与数据已保留或恢复。请返回软件后重试更新。')
                if not done:
                    done=True
                    primary('返回软件',True,app.destroy);secondary('退出软件',True,exit_application)
                    app.after(15000,app.destroy)
                return
        except (OSError,ValueError,KeyError):pass
        app.after(200,refresh)
    app.after(100,refresh)
    try:app.mainloop()
    finally:
        if private_fonts:
            import ctypes
            for font_path in private_fonts:ctypes.windll.gdi32.RemoveFontResourceExW(str(font_path),0x10,None)
