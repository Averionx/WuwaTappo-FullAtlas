"""Validated mod-release updates with a reversible file transaction."""
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
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
from process_launch import popen_independent
from update_progress import UpdateLease, read_progress, write_progress, TERMINAL

REPO = 'Averionx/WuwaTappo-FullAtlas'
TOP_LEVEL = {'WuwaTappo.Local.exe', 'LocalGalleryHost.exe', 'package_config.json',
             'launch.ps1', 'initialize.ps1', 'restore_network.ps1', 'README.md',
             'LICENSE', 'THIRD_PARTY_NOTICES.md'}
PROTECTED = {'local_config.json', 'offline_state.json', 'assistant_state.json', 'update_policy.json', 'profile', 'cache', 'runtime'}


class ReleaseNotesParser(HTMLParser):
    """Read only release notes, never the repository About or page metadata."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.complete = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if self.depth and tag in ('p','li','h1','h2','h3','h4','br','tr'):
            self.parts.append('\n' + ('• ' if tag=='li' else ''))
        if tag != 'div':return
        if self.depth:self.depth += 1
        elif not self.complete and 'markdown-body' in dict(attrs).get('class', '').split():
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth and tag in ('p','li','h1','h2','h3','h4','tr'):
            self.parts.append('\n')
        if tag == 'div' and self.depth:
            self.depth -= 1
            if not self.depth:self.complete = True

    def handle_data(self, data):
        if self.depth:self.parts.append(data)

    def text(self):
        return ''.join(self.parts) if self.complete else ''


def release_notes_text(body):
    if not isinstance(body,str):return ''
    lines=[]
    for line in body[:32000].splitlines():
        value=line.strip()
        heading=re.sub(r'^#{1,6}\s*','',value)
        if re.fullmatch(r'(下载(?:与升级)?|Downloads?|Installation|安装(?:与升级)?)[：:]?',heading,re.I):break
        if value.startswith('|') or value.startswith('!['):continue
        value=re.sub(r'\[([^\]]+)\]\([^\)]+\)',r'\1',heading)
        value=value.replace('**','').replace('`','')
        value=re.sub(r'^[-*]\s+','• ',value)
        if value or (lines and lines[-1]):lines.append(value)
    return '\n'.join(lines).strip()[:12000]


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

    def apply(self, progress=None):
        # Validate every staged byte before replacing even one installed file.
        total=sum(item['size'] for item in self.manifest['files']) or 1
        done=0
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
            deadline=time.monotonic()+30
            while True:
                try:os.replace(temp,target);break
                except PermissionError:
                    if time.monotonic()>=deadline:raise
                    if progress:progress(80+16*done/total,'等待旧文件释放后继续更新…')
                    time.sleep(.25)
            done+=item['size']
            if progress:progress(80+16*done/total,'正在备份并替换程序文件…')

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
        self.install_start_lock = threading.Lock()
        self.policy_file = self.root/'update_policy.json'
        self.last_error = None
        self.checked_at = 0
        self.official_version = config.get('client_version','')
        self.official_checked = False
        self.official_error = None
        self.waiting_for_adapter = False
        self.release_base = ''
        self.github_version = ''
        self.github_checked = False
        self.github_error = None
        self.latest_notes = ''
        self.preview_until = 0
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
            try:self.check_official()
            except Exception as error:self.official_error=str(error)
            try:
                self._check()
                self.checked_at = int(time.time())
                self.last_error = None
                self.github_error = None
                return self.status()
            except Exception as error:
                self.last_error = str(error)
                self.github_error = str(error)
                return self.status()

    def check_official(self):
        url='https://mc-wuwatappo.kurogames-global.com/app/version-json/latest.json?t='+str(int(time.time()))
        value=json.loads(self.fetch(url))
        version_tuple(value['version'])
        self.official_version=value['version'];self.official_checked=True;self.official_error=None
        current=self.config.get('client_version','')
        cached_base=(self.available or {}).get('client_version','')
        if current and version_tuple(self.official_version)>version_tuple(current):
            self.waiting_for_adapter=not cached_base or version_tuple(cached_base)<version_tuple(self.official_version)

    def _check(self):
        try:
            release = json.loads(self.fetch('https://api.github.com/repos/'+REPO+'/releases/latest'))
        except Exception:
            # Public release pages remain usable when a shared IP exhausts the
            # unauthenticated API quota. No account token is needed.
            release = self.public_release()
        version = release['tag_name'].removeprefix('v')
        version_tuple(version)
        if release.get('draft') or release.get('prerelease'):
            return self.status()
        self.github_version=version;self.github_checked=True;self.github_error=None
        self.latest_notes=release_notes_text(release.get('body',''))
        match=re.search(r'(?:适配官方(?:桌宠)?|官方基底)[\s*：:]*([0-9]+(?:\.[0-9]+){1,3})',release.get('body',''))
        self.release_base=match[1] if match else ''
        current_base=self.config.get('client_version','')
        newer_official=bool(self.official_version and current_base and version_tuple(self.official_version)>version_tuple(current_base))
        newer_mod=version_tuple(version)>version_tuple(self.config['mod_version'])
        required_base=self.official_version or current_base
        self.waiting_for_adapter=bool(required_base) and (newer_mod or newer_official) and (not newer_mod or not self.release_base or version_tuple(self.release_base)<version_tuple(required_base))
        if self.waiting_for_adapter:
            self.available=None
            atomic_json(self.policy_file,{'repository':REPO,'release':None})
            return self.status()
        if version_tuple(version) <= version_tuple(self.config['mod_version']):
            # An installed rollback must not be unlocked by a stale API response.
            if self.available:
                return self.status()
            return self.status()
        asset = next((a for a in release.get('assets',[]) if a['name']=='WuwaTappo-FullAtlas-'+version+'-x64-update.zip'), None)
        sums = next((a for a in release.get('assets',[]) if a['name']=='SHA256SUMS.txt'), None)
        prefix = 'https://github.com/'+REPO+'/releases/download/'
        if not asset or not sums or not asset['browser_download_url'].startswith(prefix) or not sums['browser_download_url'].startswith(prefix):
            self.waiting_for_adapter=newer_official
            if newer_official:self.available=None
            if self.available:
                return self.status()
            return self.status()
        entries = self.fetch(sums['browser_download_url'],65536).decode('utf-8-sig')
        match = re.search(r'^([0-9a-fA-F]{64})\s+\*?'+re.escape(asset['name'])+r'\s*$', entries, re.M)
        if not match or not 0 < asset['size'] <= 500*1024*1024:
            raise ValueError('升级包缺少有效 SHA256 校验')
        candidate = {'version':version,'url':asset['browser_download_url'],'sha256':match[1].lower(),'size':asset['size'],'notes':self.latest_notes}
        if self.release_base:candidate['client_version']=self.release_base
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
            page = response.read(2*1024*1024+1)
        if len(page)>2*1024*1024:
            raise ValueError('Release page exceeds limit')
        prefix = 'https://github.com/'+REPO+'/releases/tag/'
        if not final.startswith(prefix):
            raise ValueError('无法确定修改版发布版本')
        tag = final.removeprefix(prefix)
        version = tag.removeprefix('v')
        version_tuple(version)
        result = {'tag_name':tag,'assets':[]}
        if version_tuple(version) <= version_tuple(self.config['mod_version']):
            return result
        notes=ReleaseNotesParser()
        notes.feed(page.decode('utf-8',errors='replace'))
        notes.close()
        result['body']=notes.text()
        if not result['body'].strip():
            raise ValueError('暂时无法读取 GitHub 更新说明，请稍后重试')
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

    def start_install(self, on_ready):
        with self.install_start_lock:
            existing=read_progress(self.root)
            if existing and existing.get('phase') not in TERMINAL:
                return {'started':True,'installation':existing,'message':existing['message']}
            if not self.available or self.waiting_for_adapter:raise ValueError('请先检查可用适配更新')
            folder=self.root/'.updates'/uuid.uuid4().hex
            folder.mkdir(parents=True)
            write_progress(folder,'queued',0,'准备下载更新…')
            atomic_json(self.root/'.updates/install-current.json',{'job':folder.name,'version':self.available['version']})
            def worker():
                try:
                    result=self.prepare(folder)
                    on_ready(result)
                except Exception as error:
                    write_progress(folder,'failed',0,'更新失败：'+str(error)+'。原程序与数据保留。')
            threading.Thread(target=worker,daemon=True).start()
            return {'started':True,'installation':read_progress(self.root),'message':'正在下载更新…'}

    def prepare(self, folder=None):
        if not self.lock.acquire(blocking=False):
            raise ValueError('更新已在准备中')
        try:
            if not self.available:
                raise ValueError('请先检查更新')
            if self.waiting_for_adapter:
                raise ValueError('官方新版尚无对应适配包，请等待作者适配')
            candidate=dict(self.available)
            updates = self.root/'.updates';updates.mkdir(exist_ok=True)
            if folder is None:
                folder=updates/uuid.uuid4().hex;folder.mkdir()
            folder=Path(folder)
            archive = folder/'download.zip'
            with UpdateLease(self.root):
                expected=candidate['size'];received=0;checksum=hashlib.sha256()
                request=urllib.request.Request(candidate['url'],headers={'User-Agent':'WuwaTappo-FullAtlas-Updater'})
                write_progress(folder,'downloading',1,'正在下载升级包…',completed=0,total=expected)
                with urllib.request.urlopen(request,timeout=45) as response,archive.open('wb') as output:
                    while True:
                        chunk=response.read(256*1024)
                        if not chunk:break
                        received+=len(chunk)
                        if received>expected:raise ValueError('升级包大小超出清单')
                        output.write(chunk);checksum.update(chunk)
                        write_progress(folder,'downloading',1+59*received/expected,'正在下载升级包…',completed=received,total=expected)
                write_progress(folder,'verifying',62,'正在校验下载文件…')
                if received!=expected or checksum.hexdigest()!=candidate['sha256']:
                    raise ValueError('升级包校验失败，原程序未变动')
                write_progress(folder,'extracting',65,'正在解压并校验程序文件…')
                manifest = unpack(archive,folder/'stage')
            if manifest['version'] != candidate['version']:
                raise ValueError('Release version mismatch')
            if candidate.get('client_version') and manifest.get('client_version')!=candidate['client_version']:
                raise ValueError('官方基底与发行说明不一致，未改动原程序')
            helper = folder/'helper'
            helper.mkdir()
            shutil.copy2(self.root/'LocalGalleryHost.exe',helper/'LocalGalleryHost.exe')
            shutil.copytree(self.root/'_internal',helper/'_internal')
            atomic_json(folder/'pending.json',{'version':manifest['version'],'from_version':self.config['mod_version'],'id':folder.name})
            write_progress(folder,'waiting_exit',75,'升级包已校验，正在退出桌宠…')
            popen_independent([str(helper/'LocalGalleryHost.exe'),'--apply-update',str(self.root),str(folder/'stage')],
                             cwd=helper,creationflags=0x08000000)
            return {'restarting':True,'message':'升级包已校验。正在退出桌宠、备份并原地升级…'}
        finally:
            self.lock.release()

    def status(self):
        common={'required':False,'preview':time.monotonic()<self.preview_until,'repository':REPO,'checked_at':self.checked_at,'error':self.last_error,
                'official_version':self.official_version,'client_version':self.config.get('client_version',''),
                'current_version':self.config['mod_version'],'official_checked':self.official_checked,
                'official_error':self.official_error,'waiting_for_adapter':self.waiting_for_adapter}
        common.update(github_version=self.github_version,github_checked=self.github_checked,github_error=self.github_error)
        common['installation']=read_progress(self.root)
        common['release_notes']=(self.available or {}).get('notes','') or (self.latest_notes if not self.available or self.available['version']==self.github_version else '')
        base=self.config.get('client_version','')
        if self.official_error:
            official_state,official_message='error','官方版本检查失败，请重试。'
        elif not self.official_checked:
            official_state,official_message='unchecked','尚未检查官方最新版本。'
        elif base and version_tuple(self.official_version)>version_tuple(base):
            official_state,official_message='newer','官方已发布新版 v'+self.official_version+'（当前基底 v'+base+'）。'
        elif base and version_tuple(self.official_version)==version_tuple(base):
            official_state,official_message='current','官方最新版 v'+self.official_version+'，与当前基底版本一致。'
        else:
            official_state,official_message='known','官方最新版本为 v'+self.official_version+'。'
        if self.github_error:
            mod_state,mod_message='error','修改版更新检查失败，请重试：'+self.github_error
        elif self.waiting_for_adapter:
            mod_state,mod_message='waiting','暂未找到适配官方 v'+self.official_version+' 的可用修改版升级包，请等待作者更新。'
        elif self.available:
            mod_state,mod_message='available','发现修改版 v'+self.available['version']+'，请更新后继续使用。升级保留账号、缓存和设置。'
        elif not self.github_checked:
            mod_state,mod_message='unchecked','尚未检查修改版最新版本。'
        elif version_tuple(self.github_version)==version_tuple(self.config['mod_version']):
            mod_state,mod_message='current','修改版 v'+self.github_version+' 与当前安装版本一致，无需更新。'
        elif version_tuple(self.github_version)>version_tuple(self.config['mod_version']):
            mod_state,mod_message='pending','修改版已发布 v'+self.github_version+'，但升级包尚未准备完成，请等待作者更新。'
        else:
            mod_state,mod_message='local_newer','GitHub 最新修改版为 v'+self.github_version+'；当前安装的 v'+self.config['mod_version']+' 较新，无需更新。'
        common.update(official_state=official_state,official_message=official_message,
                      mod_state=mod_state,mod_message=mod_message)
        available=bool(self.available) and not self.waiting_for_adapter
        result={**common,'available':available,'required':available,'message':official_message+' '+mod_message}
        if available:result['version']=self.available['version']
        return result

    def healthy(self, version=None):
        if version != self.config['mod_version']:
            raise ValueError('Frontend version does not match installed package')
        for pending in (self.root/'.updates').glob('*/pending.json'):
            value = json.loads(pending.read_text(encoding='utf-8'))
            result_file=pending.parent/'result.json'
            if result_file.exists() and not json.loads(result_file.read_text(encoding='utf-8')).get('ok'):continue
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


def launch(root, job=None):
    powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    args=[str(powershell),'-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',str(root/'launch.ps1')]
    environment=dict(os.environ)
    if job:environment['WUWA_UPDATE_JOB']=job
    popen_independent(args,
                     cwd=root,creationflags=0x08000000,env=environment)


def request_graceful_exit(root):
    """Same authenticated save-and-quit action used by the app's exit button."""
    try:
        config=json.loads((Path(root)/'local_config.json').read_text(encoding='utf-8-sig'))
        port=config['port'];token=config['token']
        if type(port) is not int or not 1<=port<=65535 or not isinstance(token,str):return False
    except (OSError,ValueError,KeyError):return False
    request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/assistant/quit',data=b'{}',headers={'Content-Type':'application/json','X-Local-Token':token})
    try:
        with urllib.request.urlopen(request,timeout=5) as response:response.read(2*1024*1024)
        return True
    except OSError:return False


def apply_update(root_arg, stage_arg):
    root, stage = Path(root_arg).resolve(), Path(stage_arg).resolve()
    if not stage.is_relative_to(root/'.updates') or stage.name!='stage':
        raise ValueError('Invalid update stage')
    folder = stage.parent
    # Held through restart/health confirmation. A second helper cannot replace
    # files, restart the old EXE or roll back the first helper's transaction.
    deadline=time.monotonic()+5
    while True:
        lease=UpdateLease(root)
        try:lease.__enter__()
        except RuntimeError as error:
            progress=read_progress(root)
            if progress.get('job')==folder.name and progress.get('phase')=='queued' and time.monotonic()<deadline:
                time.sleep(.05);continue
            atomic_json(folder/'result.json',{'ok':False,'error':str(error)});return
        try:_apply_update_locked(root,stage,folder)
        finally:lease.__exit__(None,None,None)
        return


def _apply_update_locked(root,stage,folder):
    transaction = FileTransaction(root, stage)
    def report(phase,percent,message):return write_progress(folder,phase,percent,message)
    report('waiting_exit',75,'正在等待桌宠保存数据并退出…')
    if getattr(sys,'frozen',False):
        popen_independent([sys.executable,'--update-progress',str(folder)],cwd=folder,creationflags=0x08000000)
    try:
        request_graceful_exit(root)
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
        report('installing',80,'正在备份并替换程序文件…')
        transaction.apply(lambda percent,message:report('installing',percent,message))
        report('restarting',97,'正在启动新版本…')
        launch(root,folder.name)
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
        report('complete',100,'更新完成，新版本已启动。')
    except Exception as error:
        if transaction.changed:
            for proc in processes(root):
                proc.terminate()
            import psutil
            psutil.wait_procs(processes(root),timeout=10)
            transaction.rollback()
            launch(root,folder.name)
        else:
            from process_lifecycle import native_is_running
            if native_is_running(root) is False:launch(root,folder.name)
        atomic_json(folder/'result.json',{'ok':False,'error':str(error)})
        report('failed',0,'更新失败：'+str(error)+'。已保留或恢复旧版本，请重试。')
