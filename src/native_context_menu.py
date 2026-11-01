"""Native popup owned by the cache host, independent of Tauri's UI thread."""
import ctypes
from ctypes import wintypes
import os
import threading

_popup_lock=threading.Lock()
WM_CANCELMODE=0x001f
MOUSE_BUTTONS=(1,2,4)
ENUM_WINDOWS=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM) if os.name=='nt' else None
ALLOWED={'bag','atlas','exchange','room','console','setting','drag','game','hide','restart','quit'}|{'opacity-'+str(n) for n in (25,50,75,100)}|{'scale-'+str(n) for n in (50,75,100,125,150,175,200)}


def validate_items(items,depth=0):
    if not isinstance(items,list) or not 1<=len(items)<=32 or depth>1:raise ValueError('Invalid menu')
    result=[]
    for item in items:
        if not isinstance(item,dict):raise ValueError('Invalid menu item')
        if item.get('separator') is True:result.append({'separator':True});continue
        text=item.get('text')
        if not isinstance(text,str) or not 1<=len(text)<=120 or any(ord(c)<32 for c in text):raise ValueError('Invalid menu text')
        if 'items' in item:result.append({'text':text,'items':validate_items(item['items'],depth+1)})
        else:
            key=item.get('key')
            if key not in ALLOWED:raise ValueError('Unknown menu action')
            result.append({'text':text,'key':key,'checked':item.get('checked') is True})
    return result


class WindowsPopup:
    def __init__(self):
        self.api=ctypes.WinDLL('user32',use_last_error=True)
        signatures={
            'CreatePopupMenu':([],wintypes.HMENU),
            'AppendMenuW':([wintypes.HMENU,wintypes.UINT,ctypes.c_size_t,wintypes.LPCWSTR],wintypes.BOOL),
            'DestroyMenu':([wintypes.HMENU],wintypes.BOOL),
            'CreateWindowExW':([wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,wintypes.LPVOID],wintypes.HWND),
            'DestroyWindow':([wintypes.HWND],wintypes.BOOL),
            'ShowWindow':([wintypes.HWND,ctypes.c_int],wintypes.BOOL),
            'GetForegroundWindow':([],wintypes.HWND),
            'SetForegroundWindow':([wintypes.HWND],wintypes.BOOL),
            'GetCursorPos':([ctypes.POINTER(wintypes.POINT)],wintypes.BOOL),
            'TrackPopupMenuEx':([wintypes.HMENU,wintypes.UINT,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.LPVOID],wintypes.UINT),
            'PostMessageW':([wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM],wintypes.BOOL),
            'GetAsyncKeyState':([ctypes.c_int],ctypes.c_short),
            'GetWindowThreadProcessId':([wintypes.HWND,ctypes.POINTER(wintypes.DWORD)],wintypes.DWORD),
            'EnumThreadWindows':([wintypes.DWORD,ENUM_WINDOWS,wintypes.LPARAM],wintypes.BOOL),
            'GetClassNameW':([wintypes.HWND,wintypes.LPWSTR,ctypes.c_int],ctypes.c_int),
            'GetWindowRect':([wintypes.HWND,ctypes.POINTER(wintypes.RECT)],wintypes.BOOL),
            'IsWindowVisible':([wintypes.HWND],wintypes.BOOL),
        }
        for name,(args,result) in signatures.items():
            function=getattr(self.api,name);function.argtypes=args;function.restype=result

    def menu_rectangles(self,thread_id):
        rectangles=[]
        @ENUM_WINDOWS
        def visit(window,_):
            name=ctypes.create_unicode_buffer(64)
            self.api.GetClassNameW(window,name,len(name))
            if name.value=='#32768' and self.api.IsWindowVisible(window):
                rect=wintypes.RECT()
                if self.api.GetWindowRect(window,ctypes.byref(rect)):
                    rectangles.append((rect.left,rect.top,rect.right,rect.bottom))
            return True
        self.api.EnumThreadWindows(thread_id,visit,0)
        return rectangles

    def watch_dismissal(self,owner,thread_id,previous,stop):
        # A background host may not become foreground. In that case Windows
        # doesn't reliably dismiss TrackPopupMenu on outside clicks. Observe
        # physical state only, and cancel only this owner's menu. Never consume,
        # replay or modify input, or attach another app's input queue.
        buttons={key:bool(self.api.GetAsyncKeyState(key)&0x8000) for key in MOUSE_BUTTONS}
        escape=bool(self.api.GetAsyncKeyState(0x1b)&0x8000)
        try:
            while not stop.wait(.015):
                foreground=self.api.GetForegroundWindow()
                cancel=bool(foreground and foreground not in (previous,owner))
                key_state=self.api.GetAsyncKeyState(0x1b)
                pressed=bool(key_state&0x8000)
                cancel|=(pressed and not escape) or bool(key_state&1)
                escape=pressed
                clicked=False
                for key in MOUSE_BUTTONS:
                    key_state=self.api.GetAsyncKeyState(key);pressed=bool(key_state&0x8000)
                    clicked|=(pressed and not buttons[key]) or bool(key_state&1)
                    buttons[key]=pressed
                if clicked:
                    rectangles=self.menu_rectangles(thread_id)
                    point=wintypes.POINT()
                    if rectangles and self.api.GetCursorPos(ctypes.byref(point)):
                        cancel|=not any(left<=point.x<right and top<=point.y<bottom for left,top,right,bottom in rectangles)
                if cancel:
                    self.api.PostMessageW(owner,WM_CANCELMODE,0,0)
                    return
        except Exception:
            # Fail closed without leaving a menu waiting for inaccessible input.
            self.api.PostMessageW(owner,WM_CANCELMODE,0,0)

    def show(self,items):
        commands={};next_id=1;menus=[];roots=set();owner=None;watcher=None;stop=threading.Event()
        def build(entries):
            nonlocal next_id
            menu=self.api.CreatePopupMenu()
            if not menu:raise ctypes.WinError(ctypes.get_last_error())
            menus.append(menu)
            roots.add(menu)
            for item in entries:
                if item.get('separator'):ok=self.api.AppendMenuW(menu,0x800,0,None)
                elif 'items' in item:
                    child=build(item['items']);ok=self.api.AppendMenuW(menu,0x10,child,item['text'])
                    if ok:roots.discard(child)
                else:
                    identifier=next_id;next_id+=1;commands[identifier]=item['key']
                    ok=self.api.AppendMenuW(menu,0x8 if item['checked'] else 0,identifier,item['text'])
                if not ok:raise ctypes.WinError(ctypes.get_last_error())
            return menu
        previous=self.api.GetForegroundWindow()
        try:
            menu=build(items)
            # Only our own zero-sized tool window is activated.
            owner=self.api.CreateWindowExW(0x80,'STATIC','WuwaTappo context menu',0x80000000,0,0,0,0,None,None,None,None)
            if not owner:raise ctypes.WinError(ctypes.get_last_error())
            self.api.ShowWindow(owner,5);self.api.SetForegroundWindow(owner)
            point=wintypes.POINT()
            if not self.api.GetCursorPos(ctypes.byref(point)):raise ctypes.WinError(ctypes.get_last_error())
            thread_id=self.api.GetWindowThreadProcessId(owner,None)
            watcher=threading.Thread(target=self.watch_dismissal,args=(owner,thread_id,previous,stop),daemon=True)
            watcher.start()
            selected=self.api.TrackPopupMenuEx(menu,0x100|0x80|0x2,point.x,point.y,owner,None)
            self.api.PostMessageW(owner,0,0,0)
            return commands.get(selected)
        finally:
            stop.set()
            if watcher:watcher.join(timeout=1)
            if owner:
                if self.api.GetForegroundWindow()==owner and previous:self.api.SetForegroundWindow(previous)
                self.api.DestroyWindow(owner)
            # Destroying the root recursively destroys attached submenus.
            for menu in roots:self.api.DestroyMenu(menu)


def popup(items,*,implementation=None):
    items=validate_items(items)
    if not _popup_lock.acquire(blocking=False):return {'action':None,'busy':True}
    try:
        if implementation is None:
            if os.name!='nt':raise RuntimeError('Windows menu required')
            implementation=WindowsPopup()
        return {'action':implementation.show(items)}
    finally:_popup_lock.release()
