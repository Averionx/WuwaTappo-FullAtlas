"""Validated mod-release updates with a reversible file transaction."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import zipfile
from desktop_assistant import atomic_json

REPO = 'Averionx/WuwaTappo-FullAtlas'
TOP_LEVEL = {'WuwaTappo.Local.exe', 'LocalGalleryHost.exe', 'package_config.json',
             'launch.ps1', 'initialize.ps1', 'restore_network.ps1', 'README.md',
             'LICENSE', 'THIRD_PARTY_NOTICES.md'}
PROTECTED = {'local_config.json', 'offline_state.json', 'assistant_state.json', 'update_policy.json', 'profile', 'cache', 'runtime'}


def safe_name(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or path.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise ValueError('Unsafe update path')
    for part in path.parts:
        if part.endswith((' ', '.')) or any(ord(c)<32 for c in part) or re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?',part,re.I):
            raise ValueError('Unsafe Windows path')
    if path.parts[0] in PROTECTED or (len(path.parts) == 1 and name not in TOP_LEVEL) or (len(path.parts)>1 and path.parts[0] not in ('_internal', 'licenses', 'docs')):
        raise ValueError('Update tried to replace data or an unknown component')
    return path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def version_tuple(value):
    if not re.fullmatch(r'\d+(\.\d+){1,3}', value):
        raise ValueError('Invalid release version')
    return tuple(int(x) for x in value.split('.')) + (0,) * (4-len(value.split('.')))


def validate_manifest(manifest):
    if manifest.get('schema') != 1:
        raise ValueError('Unknown update format')
    version_tuple(manifest['version'])
    files = manifest['files']
    if not isinstance(files, list) or not 3 <= len(files) <= 5000:
        raise ValueError('Invalid update inventory')
    seen = set()
    total = 0
    for item in files:
        safe_name(item['path'])
        key = item['path'].casefold()
        if key in seen or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('Duplicate path or invalid hash')
        seen.add(key)
        if type(item['size']) is not int or not 0 <= item['size'] <= 300*1024*1024:
            raise ValueError('Invalid update size')
        total += item['size']
    if total > 1024*1024*1024:
        raise ValueError('Update too large')
    if not {'wuwatappo.local.exe','localgalleryhost.exe','package_config.json'} <= seen:
        raise ValueError('Missing executable or public configuration')
    return manifest


def unpack(archive, stage):
    stage = Path(stage)
    stage.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        info = z.getinfo('update_manifest.json')
        if info.file_size > 2*1024*1024:
            raise ValueError('Manifest too large')
        manifest = validate_manifest(json.loads(z.read(info)))
        inventory = {x['path']: x for x in manifest['files']}
        if len(z.infolist()) != len(inventory)+1 or set(z.namelist()) != set(inventory)|{'update_manifest.json'}:
            raise ValueError('Archive inventory mismatch')
        for name, item in inventory.items():
            info = z.getinfo(name)
            if info.file_size != item['size'] or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Invalid archive entry')
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as source, target.open('wb') as dest:
                shutil.copyfileobj(source, dest)
            if digest(target) != item['sha256']:
                raise ValueError('Update hash mismatch')
    config = json.loads((stage/'package_config.json').read_text(encoding='utf-8-sig'))
    if 'token' in config or config.get('mod_version') != manifest['version']:
        raise ValueError('Invalid public configuration')
    atomic_json(stage/'update_manifest.json', manifest)
    return manifest


class FileTransaction:
    def __init__(self, root, stage):
        self.root, self.stage = Path(root).resolve(), Path(stage).resolve()
        self.manifest = validate_manifest(json.loads((self.stage/'update_manifest.json').read_text(encoding='utf-8')))
        self.backup = self.stage.parent/'backup'
        self.changed = []

    def apply(self):
        # Validate every staged byte before replacing even one installed file.
        for item in self.manifest['files']:
            source = self.stage/item['path']
            if not source.is_file() or source.stat().st_size != item['size'] or digest(source) != item['sha256']:
                raise ValueError('Staged content changed')
            target = self.root/item['path']
            if not target.resolve().is_relative_to(self.root) or target.is_symlink():
                raise ValueError('Target escapes installation')
        for item in self.manifest['files']:
            name = item['path']
            source, target, backup = self.stage/name, self.root/name, self.backup/name
            existed = target.exists()
            if existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            self.changed.append({'path': name, 'existed': existed})
            atomic_json(self.stage.parent/'transaction.json', self.changed)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name+'.update-tmp')
            shutil.copy2(source, temp)
            os.replace(temp, target)

    def rollback(self):
        for item in reversed(self.changed):
            target = self.root/item['path']
            if item['existed']:
                shutil.copy2(self.backup/item['path'], target)
            elif target.exists():
                target.unlink()


class Updater:
    def __init__(self, root, config):
        self.root, self.config = Path(root), config
        self.available = None
        self.lock = threading.Lock()
        self.check_lock = threading.Lock()
        self.policy_file = self.root/'update_policy.json'
        self.last_error = None
        self.checked_at = 0
        if self.policy_file.exists():
            try:
                saved = json.loads(self.policy_file.read_text(encoding='utf-8'))
                candidate = saved.get('release')
                if candidate and self.valid_candidate(candidate) and version_tuple(candidate['version']) > version_tuple(config['mod_version']):
                    self.available = candidate
            except (ValueError, KeyError, TypeError):
                pass

    @staticmethod
    def valid_candidate(value):
        version = value['version']
        version_tuple(version)
        prefix = 'https://github.com/'+REPO+'/releases/download/v'+version+'/'
        other = 'https://github.com/'+REPO+'/releases/download/'+version+'/'
        return (isinstance(value['url'], str) and value['url'].startswith((prefix, other)) and
                re.fullmatch('[0-9a-f]{64}', value['sha256']) and
                type(value['size']) is int and 0 < value['size'] <= 500*1024*1024)

    def fetch(self, url, max_size=2*1024*1024):
        req = urllib.request.Request(url, headers={'User-Agent':'WuwaTappo-FullAtlas-Updater','Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=45) as response:
            data = response.read(max_size+1)
        if len(data)>max_size:
            raise ValueError('Download exceeds limit')
        return data

    def check(self):
        with self.check_lock:
            try:
                result = self._check()
                self.checked_at = int(time.time())
                self.last_error = None
                return {**self.status(), **result}
            except Exception as error:
                self.last_error = str(error)
                # A verified mandatory release stays required across outages.
                if self.available:
                    return self.status()
                raise

    def _check(self):
        try:
            release = json.loads(self.fetch('https://api.github.com/repos/'+REPO+'/releases/latest'))
        except Exception:
            # Public release pages remain usable when a shared IP exhausts the
            # unauthenticated API quota. No account token is needed.
            release = self.public_release()
        version = release['tag_name'].removeprefix('v')
        if release.get('draft') or release.get('prerelease'):
            return self.status()
        if version_tuple(version) <= version_tuple(self.config['mod_version']):
            # An installed rollback must not be unlocked by a stale API response.
            if self.available:
                return self.status()
            return {'available':False,'message':'当前修改版 '+self.config['mod_version']+'，已是最新适配版本。'}
        asset = next((a for a in release.get('assets',[]) if a['name']=='WuwaTappo-FullAtlas-'+version+'-x64-update.zip'), None)
        sums = next((a for a in release.get('assets',[]) if a['name']=='SHA256SUMS.txt'), None)
        prefix = 'https://github.com/'+REPO+'/releases/download/'
        if not asset or not sums or not asset['browser_download_url'].startswith(prefix) or not sums['browser_download_url'].startswith(prefix):
            if self.available:
                return self.status()
            return {'available':False,'message':'检测到新版本，但尚无兼容的原地升级包；当前版本保持不变。'}
        entries = self.fetch(sums['browser_download_url'],65536).decode('utf-8-sig')
        match = re.search(r'^([0-9a-fA-F]{64})\s+\*?'+re.escape(asset['name'])+r'\s*$', entries, re.M)
        if not match or not 0 < asset['size'] <= 500*1024*1024:
            raise ValueError('升级包缺少有效 SHA256 校验')
        candidate = {'version':version,'url':asset['browser_download_url'],'sha256':match[1].lower(),'size':asset['size']}
        if not self.valid_candidate(candidate):
            raise ValueError('Invalid release download destination')
        if self.available and version_tuple(self.available['version']) > version_tuple(version):
            return self.status()
        self.available = candidate
        atomic_json(self.policy_file, {'repository':REPO,'release':self.available})
        return self.status()

    def public_release(self):
        request = urllib.request.Request('https://github.com/'+REPO+'/releases/latest',headers={'User-Agent':'WuwaTappo-FullAtlas-Updater'})
        with urllib.request.urlopen(request,timeout=45) as response:
            final = response.geturl()
        prefix = 'https://github.com/'+REPO+'/releases/tag/'
        if not final.startswith(prefix):
            raise ValueError('无法确定修改版发布版本')
        tag = final.removeprefix(prefix)
        version = tag.removeprefix('v')
        version_tuple(version)
        result = {'tag_name':tag,'assets':[]}
        if version_tuple(version) <= version_tuple(self.config['mod_version']):
            return result
        base = 'https://github.com/'+REPO+'/releases/download/'+tag+'/'
        name = 'WuwaTappo-FullAtlas-'+version+'-x64-update.zip'
        try:
            with urllib.request.urlopen(urllib.request.Request(base+name,method='HEAD',headers={'User-Agent':'WuwaTappo-FullAtlas-Updater'}),timeout=45) as response:
                size = int(response.headers.get('Content-Length','0'))
            result['assets'] = [{'name':name,'browser_download_url':base+name,'size':size},
                                {'name':'SHA256SUMS.txt','browser_download_url':base+'SHA256SUMS.txt'}]
        except Exception:
            pass
        return result

    def prepare(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError('更新已在准备中')
        try:
            if not self.available:
                raise ValueError('请先检查更新')
            updates = self.root/'.updates'
            updates.mkdir(exist_ok=True)
            folder = updates/uuid.uuid4().hex
            folder.mkdir()
            archive = folder/'download.zip'
            data = self.fetch(self.available['url'],self.available['size'])
            if len(data)!=self.available['size'] or hashlib.sha256(data).hexdigest()!=self.available['sha256']:
                raise ValueError('升级包校验失败，原程序未变动')
            archive.write_bytes(data)
            manifest = unpack(archive,folder/'stage')
            if manifest['version'] != self.available['version']:
                raise ValueError('Release version mismatch')
            helper = folder/'helper'
            helper.mkdir()
            shutil.copy2(self.root/'LocalGalleryHost.exe',helper/'LocalGalleryHost.exe')
            shutil.copytree(self.root/'_internal',helper/'_internal')
            atomic_json(folder/'pending.json',{'version':manifest['version'],'id':folder.name})
            subprocess.Popen([str(helper/'LocalGalleryHost.exe'),'--apply-update',str(self.root),str(folder/'stage')],
                             cwd=helper,creationflags=0x08000000)
            return {'restarting':True,'message':'升级包已校验。正在退出桌宠、备份并原地升级…'}
        finally:
            self.lock.release()

    def status(self):
        if self.available:
            return {'available':True,'required':True,'version':self.available['version'],
                    'repository':REPO,'checked_at':self.checked_at,'error':self.last_error,
                    'message':'必须更新至 '+self.available['version']+' 才能继续使用。升级保留账号、缓存和设置。'}
        return {'available':False,'required':False,'repository':REPO,'checked_at':self.checked_at,
                'error':self.last_error,'message':'当前修改版 '+self.config['mod_version']}

    def healthy(self, version=None):
        if version != self.config['mod_version']:
            raise ValueError('Frontend version does not match installed package')
        for pending in (self.root/'.updates').glob('*/pending.json'):
            value = json.loads(pending.read_text(encoding='utf-8'))
            if value['version'] == self.config['mod_version']:
                (pending.parent/'healthy').write_text(value['version'],encoding='utf-8')
        return {'ok':True}


def processes(root):
    import psutil
    root = Path(root).resolve()
    result = []
    for proc in psutil.process_iter(['pid','exe']):
        try:
            exe = Path(proc.info['exe'] or '')
            if exe.is_file() and exe.resolve().is_relative_to(root) and '.updates' not in exe.parts and exe.name.lower() in ('wuwatappo.local.exe','localgalleryhost.exe','msedgewebview2.exe'):
                result.append(proc)
        except (OSError, psutil.Error):
            pass
    return result


def launch(root):
    powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.Popen([str(powershell),'-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',str(root/'launch.ps1')],
                     cwd=root,creationflags=0x08000000)


def apply_update(root_arg, stage_arg):
    root, stage = Path(root_arg).resolve(), Path(stage_arg).resolve()
    if not stage.is_relative_to(root/'.updates') or stage.name!='stage':
        raise ValueError('Invalid update stage')
    folder = stage.parent
    transaction = FileTransaction(root, stage)
    try:
        # Original exit flow persists counters. Never force-close the old app.
        deadline = time.monotonic()+60
        while processes(root):
            running = processes(root)
            if not any(Path(p.exe()).name.lower()=='wuwatappo.local.exe' for p in running):
                # v1.0's host has no quit endpoint. Once its app has exited, it
                # holds no unsaved renderer counters; stop only that exact host.
                for proc in running:
                    if Path(proc.exe()).resolve() == root/'LocalGalleryHost.exe':
                        proc.terminate()
            if time.monotonic()>deadline:
                raise TimeoutError('旧桌宠仍在运行，升级取消；原文件未替换。')
            time.sleep(.5)
        transaction.apply()
        launch(root)
        deadline = time.monotonic()+90
        while not (folder/'healthy').exists():
            if time.monotonic()>deadline:
                raise TimeoutError('新版本未通过启动检查，正在恢复旧版本。')
            time.sleep(.5)
        # Only delete this verified update's own backup, after renderer acknowledgment.
        if transaction.backup.resolve().is_relative_to(root/'.updates') and transaction.backup.exists():
            shutil.rmtree(transaction.backup)
        if stage.resolve().is_relative_to(root/'.updates'):
            shutil.rmtree(stage)
        (folder/'download.zip').unlink(missing_ok=True)
        (folder/'pending.json').unlink(missing_ok=True)
        atomic_json(folder/'result.json',{'ok':True,'version':transaction.manifest['version']})
    except Exception as error:
        if transaction.changed:
            for proc in processes(root):
                proc.terminate()
            import psutil
            psutil.wait_procs(processes(root),timeout=10)
            transaction.rollback()
            launch(root)
        else:
            # The old application may still be open, but its host already exited.
            launch(root)
        atomic_json(folder/'result.json',{'ok':False,'error':str(error)})
