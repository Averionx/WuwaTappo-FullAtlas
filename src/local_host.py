"""Local cache host and executable-scoped Windows Firewall switch."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import sys
import argparse, base64, ctypes, hashlib, json, mimetypes, subprocess, threading, time, re
from sync_cache import sync as sync_public_cache

ROOT = Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
CONFIG = json.loads((ROOT / 'local_config.json').read_text(encoding='utf-8-sig'))
PORT = CONFIG['port']
TOKEN = CONFIG['token']
STATE = ROOT / 'offline_state.json'
LOCK = threading.RLock()
PROGRAMS = [ROOT / 'WuwaTappo.Local.exe', ROOT / 'runtime/msedgewebview2.exe']
PREFIX = 'WuwaTappo.LocalGallery.' + hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:12]
PS = str(Path(__import__('os').environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')

def powershell(source):
    source = "$ProgressPreference='SilentlyContinue';" + source
    encoded = base64.b64encode(source.encode('utf-16le')).decode('ascii')
    proc = subprocess.run([PS, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                          capture_output=True, encoding='utf-8', errors='replace',
                          creationflags=0x08000000, timeout=60)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or 'Firewall operation failed')
    return proc.stdout.strip()

def quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def desired_offline():
    try:
        return json.loads(STATE.read_text(encoding='utf-8')).get('enabled') is True
    except (OSError, ValueError):
        return False

def firewall_query():
    # Check active policy, rule action, direction, all profiles, and executable filter.
    checks = []
    for index, program in enumerate(PROGRAMS):
        for suffix, direction in [('Out', 'Outbound'), ('In', 'Inbound')]:
            name = f'{PREFIX}.{index}.{suffix}'
            checks.append(
                f"$r=Get-NetFirewallRule -PolicyStore ActiveStore -Name {quote(name)} -ErrorAction SilentlyContinue;"
                f"if(!$r -or $r.Enabled -ne 'True' -or $r.Action -ne 'Block' -or $r.Direction -ne '{direction}' "
                f"-or $r.Profile -ne 'Any'){{$ok=$false}}else{{"
                f"$p=$r|Get-NetFirewallApplicationFilter;if($p.Program -ne {quote(program)}){{$ok=$false}}}};")
    source = ("$ErrorActionPreference='Stop';$ok=$true;"
              "if(@(Get-NetFirewallProfile -PolicyStore ActiveStore|Where-Object {!$_.Enabled}).Count){$ok=$false};"
              + ''.join(checks) + "if($ok){'true'}else{'false'}")
    return powershell(source).splitlines()[-1:] == ['true']

def set_firewall(enabled):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('需要通过本地版启动器授予 Windows 管理员权限，才能验证系统防火墙断网。')
    source = "$ErrorActionPreference='Stop';"
    if enabled:
        source += ("if(@(Get-NetFirewallProfile -PolicyStore ActiveStore|Where-Object {!$_.Enabled}).Count)"
                   "{throw 'Windows Firewall has a disabled profile; offline mode was not enabled.'};")
    for index, program in enumerate(PROGRAMS):
        if not program.is_file():
            raise FileNotFoundError(program)
        for suffix, direction in [('Out', 'Outbound'), ('In', 'Inbound')]:
            name = f'{PREFIX}.{index}.{suffix}'
            source += f"Get-NetFirewallRule -Name {quote(name)} -ErrorAction SilentlyContinue|Remove-NetFirewallRule;"
            if enabled:
                source += (f"New-NetFirewallRule -Name {quote(name)} -DisplayName {quote(name)} "
                           f"-Direction {direction} -Action Block -Enabled True -Profile Any "
                           f"-Program {quote(program)} -Protocol Any|Out-Null;")
    powershell(source + 'exit 0;')
    if enabled and not firewall_query():
        raise RuntimeError('系统防火墙规则未通过验证，未开启本地图鉴。')

def cache_ready():
    try:
        manifest = json.loads((ROOT / 'cache/asset_manifest.json').read_text(encoding='utf-8'))
        return not manifest['errors'] and len(manifest['records']) == CONFIG['asset_count'] and all(
            (ROOT / 'cache/assets' / r['file']).stat().st_size == r['size'] for r in manifest['records'])
    except (OSError, ValueError, KeyError):
        return False

READY = cache_ready()
ACTUAL_OFFLINE = False
SYNC = {'status': 'idle', 'done': 0, 'total': 0, 'checked_at': 0}

def start_sync(force=False):
    global READY
    with LOCK:
        if ACTUAL_OFFLINE:
            raise RuntimeError('本地全图鉴开启时禁止联网同步。请先关闭开关。')
        if SYNC['status'] == 'running':
            return dict(SYNC)
        if not force and time.time() - SYNC['checked_at'] < 900:
            return dict(SYNC)
        SYNC.update(status='running', done=0, total=0, error=None)
    def worker():
        global READY
        try:
            def progress(done, total):
                SYNC.update(done=done, total=total)
            result = sync_public_cache(ROOT, progress)
            with LOCK:
                CONFIG.update(asset_count=result['asset_count'], atlas_count=result['atlas_count'])
                (ROOT / 'local_config.json').write_text(json.dumps(CONFIG, indent=2), encoding='utf-8')
                READY = cache_ready()
                SYNC.update(status='complete', result=result, checked_at=time.time())
        except Exception as error:
            with LOCK:
                SYNC.update(status='failed', error=str(error), checked_at=time.time())
    threading.Thread(target=worker, daemon=True).start()
    return dict(SYNC)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def headers_common(self):
        origin = self.headers.get('Origin', '')
        if origin in ['http://tauri.localhost', 'https://tauri.localhost', 'tauri://localhost']:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Local-Token')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Cross-Origin-Resource-Policy', 'cross-origin')
        self.send_header('Cache-Control', 'no-store')

    def respond(self, code, data, content_type='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.headers_common()
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.respond(200, {})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/bootstrap':
            if self.headers.get('Origin') not in ['http://tauri.localhost','https://tauri.localhost','tauri://localhost']:
                return self.respond(403, {'error':'App origin required'})
            return self.respond(200, {'token':TOKEN})
        if path == '/status':
            return self.respond(200, {'ready': READY, 'enabled': ACTUAL_OFFLINE,
                                      'firewall_verified': ACTUAL_OFFLINE,
                                      'asset_count': CONFIG['asset_count'], 'atlas_count': CONFIG['atlas_count'], 'sync': dict(SYNC)})
        if path == '/sync/status':
            return self.respond(200, dict(SYNC))
        if path == '/offline-data':
            return self.respond(200, {'catalog': json.loads((ROOT / 'cache/offline_catalog.json').read_text(encoding='utf-8')),
                                      'atlas': json.loads((ROOT / 'cache/atlas.json').read_text(encoding='utf-8'))['data'],
                                      'atlas_count': CONFIG['atlas_count'], 'asset_count': CONFIG['asset_count']})
        # Several official preview paths rebuild a type folder from the file
        # key. Cached file keys are content-addressed, so serve those aliases
        # from the same verified cache rather than falling back to the CDN.
        if path.startswith(('/character/', '/accessory/', '/emote/', '/emote_atlas/', '/character_skin_atlas/', '/accessory_atlas/')):
            name = path.rsplit('/', 1)[-1]
            if re.fullmatch(r'[0-9a-f]{64}\.png', name):
                cached = ROOT / 'cache/assets' / name
                if cached.is_file():
                    return self.respond(200, cached.read_bytes(), 'image/png')
        if path.startswith('/assets/'):
            name = path.removeprefix('/assets/')
            if '/' in name or '\\' in name or '..' in name:
                return self.respond(400, {'error': 'Invalid path'})
            p = ROOT / 'cache/assets' / name
            if p.is_file():
                return self.respond(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            with LOCK, (ROOT / 'client_diagnostics.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'kind': 'asset_not_found', 'path': path}) + '\n')
        return self.respond(404, {'error': 'Not found'})

    def do_POST(self):
        global ACTUAL_OFFLINE
        if self.headers.get('Origin') not in [None,'http://tauri.localhost','https://tauri.localhost','tauri://localhost']:
            return self.respond(403, {'error':'App origin required'})
        if self.headers.get('X-Local-Token') != TOKEN:
            return self.respond(403, {'error': 'Invalid local control token'})
        if urlparse(self.path).path == '/sync':
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or b'{}')
                return self.respond(200, start_sync(body.get('force') is True))
            except Exception as error:
                return self.respond(409, {'error': str(error)})
        if urlparse(self.path).path == '/diagnostic':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length > 8192:
                    raise ValueError('Diagnostic too large')
                payload = json.loads(self.rfile.read(length))
                with LOCK, (ROOT / 'client_diagnostics.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(payload, ensure_ascii=False) + '\n')
                return self.respond(200, {'ok': True})
            except Exception as error:
                return self.respond(400, {'error': str(error)})
        if urlparse(self.path).path != '/mode':
            return self.respond(404, {'error': 'Not found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 1024:
                raise ValueError('Request too large')
            body = json.loads(self.rfile.read(length))
            enabled = body['enabled']
            if not isinstance(enabled, bool):
                raise ValueError('enabled must be boolean')
            with LOCK:
                if enabled and SYNC['status'] == 'running':
                    raise RuntimeError('正在同步新图鉴，请同步完成后再开启离线全图鉴。')
                if enabled and not READY:
                    raise RuntimeError('离线素材缓存不完整，未开启。')
                set_firewall(enabled)
                ACTUAL_OFFLINE = enabled
                tmp = STATE.with_suffix('.tmp')
                tmp.write_text(json.dumps({'enabled': enabled}), encoding='utf-8')
                tmp.replace(STATE)
            return self.respond(200, {'enabled': enabled, 'firewall_verified': enabled, 'ready': READY})
        except Exception as error:
            return self.respond(409, {'error': str(error)})

def main():
    global ACTUAL_OFFLINE
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore-firewall', action='store_true')
    args = parser.parse_args()
    if args.restore_firewall:
        set_firewall(False)
        STATE.write_text('{"enabled":false}', encoding='utf-8')
        return
    if desired_offline():
        if not READY:
            raise RuntimeError('Offline mode is saved but cache is incomplete; refusing to launch host.')
        set_firewall(True)
        ACTUAL_OFFLINE = True
    else:
        set_firewall(False)
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(json.dumps({'ready': READY, 'enabled': ACTUAL_OFFLINE, 'port': PORT}), flush=True)
    server.serve_forever()

if __name__ == '__main__':
    main()
