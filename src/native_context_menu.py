"""Native popup owned by the cache host, independent of Tauri's UI thread."""
import ctypes
from ctypes import wintypes
import os
import threading

_popup_lock=threading.Lock()
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
        }
        for name,(args,result) in signatures.items():
            function=getattr(self.api,name);function.argtypes=args;function.restype=result

    def show(self,items):
        commands={};next_id=1;menus=[];roots=set();owner=None
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
            # Only our own zero-sized tool window is activated. No cursor
            # clipping, pointer movement, hooks or synthetic input are used.
            owner=self.api.CreateWindowExW(0x80,'STATIC','WuwaTappo context menu',0x80000000,0,0,0,0,None,None,None,None)
            if not owner:raise ctypes.WinError(ctypes.get_last_error())
            self.api.ShowWindow(owner,5);self.api.SetForegroundWindow(owner)
            point=wintypes.POINT()
            if not self.api.GetCursorPos(ctypes.byref(point)):raise ctypes.WinError(ctypes.get_last_error())
            selected=self.api.TrackPopupMenuEx(menu,0x100|0x80|0x2,point.x,point.y,owner,None)
            self.api.PostMessageW(owner,0,0,0)
            return commands.get(selected)
        finally:
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
