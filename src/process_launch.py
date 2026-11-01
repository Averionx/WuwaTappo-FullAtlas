"""Launch independent processes without inheriting frozen runtime DLL paths."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import subprocess


@contextmanager
def clean_dll_search_path():
    if os.name!='nt':
        yield
        return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    get=kernel.GetDllDirectoryW;get.argtypes=[wintypes.DWORD,wintypes.LPWSTR];get.restype=wintypes.DWORD
    set_path=kernel.SetDllDirectoryW;set_path.argtypes=[wintypes.LPCWSTR];set_path.restype=wintypes.BOOL
    size=get(0,None);buffer=ctypes.create_unicode_buffer(size+1)
    if size:get(len(buffer),buffer)
    saved=buffer.value
    if not set_path(None):raise ctypes.WinError(ctypes.get_last_error())
    try:yield
    finally:set_path(saved or None)


def popen_independent(args,**kwargs):
    env=dict(kwargs.pop('env',None) or os.environ)
    env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    with clean_dll_search_path():
        return subprocess.Popen(args,env=env,**kwargs)
