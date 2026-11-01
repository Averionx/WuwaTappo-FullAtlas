"""Single-EXE portable launcher; persistent files live beside the launcher."""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import argparse
import ctypes
import hashlib
import json
import os
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from process_launch import popen_independent
from process_lifecycle import native_is_running

ROOT_FILES={'WuwaTappo.Local.exe','LocalGalleryHost.exe','package_config.json',
            'launch.ps1','initialize.ps1','restore_network.ps1','README.md','LICENSE',
            'THIRD_PARTY_NOTICES.md','VCRUNTIME140.dll','VCRUNTIME140_1.dll'}
ROOT_DIRS={'_internal','runtime','cache','docs','licenses'}
CRITICAL=('WuwaTappo.Local.exe','LocalGalleryHost.exe','launch.ps1',
          '_internal/python312.dll','runtime/msedgewebview2.exe','cache/atlas.json')


def version(value):
    parts=value.split('.')
    if not 2<=len(parts)<=4 or not all(x.isdigit() for x in parts):
        raise ValueError('绿色版版本信息损坏')
    return tuple(map(int,parts))+(0,)*(4-len(parts))


def safe_path(name):
    p=PurePosixPath(name)
    if not isinstance(name,str) or '\\' in name or ':' in name or p.is_absolute() or not p.parts or p.as_posix()!=name:
        raise ValueError('绿色版资源路径无效')
    if any(x in ('.','..') or x.endswith((' ','.')) for x in p.parts):
        raise ValueError('绿色版资源路径无效')
    if len(p.parts)==1 and name not in ROOT_FILES or len(p.parts)>1 and p.parts[0] not in ROOT_DIRS:
        raise ValueError('绿色版包含不允许覆盖的文件')
    return p


def read_manifest(archive):
    data=archive.read('portable_manifest.json')
    if len(data)>4*1024*1024:raise ValueError('绿色版清单过大')
    manifest=json.loads(data)
    if manifest.get('schema')!=1:raise ValueError('绿色版清单版本不兼容')
    version(manifest['version'])
    files=manifest['files']
    if not isinstance(files,list) or not 1<=len(files)<=12000:raise ValueError('绿色版清单无效')
    seen=set();total=0
    for item in files:
        name=item['path'];safe_path(name)
        if name.casefold() in seen:raise ValueError('绿色版包含重复路径')
        seen.add(name.casefold())
        if type(item['size']) is not int or not 0<=item['size']<=2*1024**3:raise ValueError('绿色版文件大小无效')
        digest=item['sha256']
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('绿色版校验值无效')
        info=archive.getinfo(name)
        if info.file_size!=item['size'] or info.is_dir() or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('绿色版文件清单不匹配')
        total+=item['size']
    if total>5*1024**3:raise ValueError('绿色版资源超过大小限制')
    names=archive.namelist()
    if len(set(n.casefold() for n in names))!=len(names) or set(names)!={x['path'] for x in files}|{'portable_manifest.json'}:
        raise ValueError('绿色版包含清单外文件')
    if not set(CRITICAL+('package_config.json','initialize.ps1')).issubset(names):
        raise ValueError('绿色版缺少必要运行文件')
    return manifest,hashlib.sha256(data).hexdigest()


def within(root,name):
    target=root.joinpath(*safe_path(name).parts)
    if not target.resolve().is_relative_to(root.resolve()):raise ValueError('绿色版目标路径超出数据目录')
    for item in (target,*target.parents):
        if item==root.parent:break
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ValueError('绿色版数据目录不能包含路径链接')
    return target


def prepare(archive_path,root):
    root=Path(root)
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise ValueError('绿色版数据目录不能是路径链接')
    root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        manifest,identity=read_manifest(archive)
        package=root/'package_config.json'
        if package.exists():
            current=json.loads(package.read_text(encoding='utf-8-sig'))
            # In-app upgrades update the persistent application. An older outer
            # launcher must never restore its bundled, older application.
            if version(current['mod_version'])>version(manifest['version']):return 'newer-installed'
        ready=root/'portable_ready.json'
        if ready.exists():
            try:
                if json.loads(ready.read_text())['identity']==identity and all(within(root,n).is_file() for n in CRITICAL):return 'ready'
            except (ValueError,KeyError):pass
        for item in manifest['files']:
            target=within(root,item['path'])
            # A live material refresh can be newer than the embedded cache.
            if item['path'].startswith('cache/') and target.is_file():continue
            target.parent.mkdir(parents=True,exist_ok=True)
            fd,temp_name=tempfile.mkstemp(prefix='.portable-',dir=target.parent)
            temp=Path(temp_name)
            try:
                digest=hashlib.sha256()
                with os.fdopen(fd,'wb') as output,archive.open(item['path']) as source:
                    while block:=source.read(1024*1024):output.write(block);digest.update(block)
                if digest.hexdigest()!=item['sha256']:raise ValueError('绿色版文件校验失败：'+item['path'])
                temp.replace(target)
            finally:temp.unlink(missing_ok=True)
        pending=ready.with_suffix('.tmp')
        pending.write_text(json.dumps({'version':manifest['version'],'identity':identity}),encoding='utf-8')
        pending.replace(ready)
        return 'prepared'


@contextmanager
def exclusive(root):
    import msvcrt
    root.mkdir(parents=True,exist_ok=True)
    with (root/'portable.lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('绿色版正在准备启动，请稍候。') from None
        try:yield
        finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def already_running(root,*,probe=None,clock=time.monotonic,wait=time.sleep):
    def port_in_use():
        with socket.socket() as sock:
            sock.settimeout(.5)
            return sock.connect_ex(('127.0.0.1',43229))==0
    probe=probe or port_in_use
    if not probe():return False
    if native_is_running(root) is True:
        try:
            config=json.loads((root/'local_config.json').read_text(encoding='utf-8-sig'))
            request=urllib.request.Request('http://127.0.0.1:43229/assistant/open-settings',
                data=b'{"view":"overview"}',headers={'Content-Type':'application/json','X-Local-Token':config['token']})
            with urllib.request.urlopen(request,timeout=3):return True
        except (OSError,ValueError,KeyError):pass
    # A just-closed pet's host gets a short grace period to save and retire.
    deadline=clock()+12
    while probe():
        if clock()>=deadline:
            raise RuntimeError('另一份全图鉴版或其他程序正在占用本地服务。请先退出正在运行的全图鉴版，再启动绿色版。')
        wait(.4)
    return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check',type=Path,help='Verify embedded files and write a QA receipt without launching the pet')
    args=parser.parse_args()
    bundle=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'portable-payload.zip'
    if args.self_check:
        with zipfile.ZipFile(bundle) as archive:
            manifest,_=read_manifest(archive)
            for item in manifest['files']:
                with archive.open(item['path']) as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise ValueError('绿色版校验失败')
        args.self_check.write_text(json.dumps({'ok':True,'version':manifest['version'],'files':len(manifest['files'])}),encoding='utf-8')
        return
    root=Path(sys.executable).resolve().parent/'WuwaTappoPortableData'
    with exclusive(root):
        if already_running(root):return
        prepare(bundle,root)
        powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        popen_independent([str(powershell),'-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',str(root/'launch.ps1')],cwd=root,creationflags=0x08000000)


if __name__=='__main__':
    try:main()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(None,str(error),'WuwaTappo全图鉴版 · 绿色版启动失败',0x10)
        sys.exit(1)
