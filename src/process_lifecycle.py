"""Retire this installation's cache host after its native pet exits."""
from pathlib import Path
import threading
import time


def native_is_running(root):
    import psutil
    expected=(Path(root)/'WuwaTappo.Local.exe').resolve()
    unknown=False
    for process in psutil.process_iter(['name','exe']):
        try:
            if (process.info.get('name') or '').lower()!='wuwatappo.local.exe':continue
            executable=process.info.get('exe')
            if not executable:unknown=True
            elif Path(executable).resolve()==expected:return True
        except (OSError,psutil.Error):unknown=True
    return None if unknown else False


def watch_native_exit(root,stop,*,stop_event=None,scan=None,clock=time.monotonic,wait=time.sleep,grace=5):
    stop_event=stop_event or threading.Event()
    scan=scan or native_is_running
    seen=False;missing_since=None
    while not stop_event.is_set():
        alive=scan(root)
        if alive is True:seen=True;missing_since=None
        elif alive is None:missing_since=None
        elif seen:
            now=clock()
            if missing_since is None:missing_since=now
            elif now-missing_since>=grace:
                stop()
                return
        wait(1)
