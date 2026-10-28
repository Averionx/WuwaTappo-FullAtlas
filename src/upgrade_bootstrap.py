"""One-file upgrade from mod 1.0; never requires installing the official app."""
from pathlib import Path
import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import uuid
from desktop_assistant import atomic_json
from desktop_updater import apply_update, unpack


def locate():
    import winreg
    key=r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B0A64B37-C7C3-4E2F-925B-A4EBB90E92B2}_is1'
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,key,0,winreg.KEY_READ|view) as handle:
                    location=Path(winreg.QueryValueEx(handle,'InstallLocation')[0])
                    if (location/'WuwaTappo.Local.exe').is_file():return location
            except OSError:pass
    known=Path(r'D:\WuwaTappoFullAtlas')
    if (known/'WuwaTappo.Local.exe').is_file():return known
    raise ValueError('未找到已安装的全图鉴版。请使用完整安装包，或通过 --target 指定现有目录。')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path)
    parser.add_argument('--apply-update',nargs=2)
    args=parser.parse_args()
    if args.apply_update:
        apply_update(*args.apply_update)
        return
    root=(args.target or locate()).resolve()
    if not all((root/name).is_file() for name in ('WuwaTappo.Local.exe','LocalGalleryHost.exe','local_config.json','launch.ps1')):
        raise ValueError('目标不是已安装的全图鉴版，未改动文件。')
    archive=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'upgrade-payload.zip'
    folder=root/'.updates'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    manifest=unpack(archive,folder/'stage')
    atomic_json(folder/'pending.json',{'version':manifest['version'],'id':folder.name})
    # A separate copy survives replacement of every installed executable.
    helper=folder/'Upgrade.exe'
    shutil.copy2(sys.executable,helper)
    subprocess.Popen([str(helper),'--apply-update',str(root),str(folder/'stage')],
                     cwd=folder,creationflags=0x08000000)


if __name__=='__main__':
    try:main()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(None,str(error),'WuwaTappo全图鉴版 · 升级失败',0x10)
        sys.exit(1)
