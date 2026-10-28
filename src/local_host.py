"""Local cache host and executable-scoped Windows Firewall switch."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import sys
import argparse, base64, ctypes, hashlib, json, mimetypes, subprocess, threading, time, re
from sync_cache import sync as sync_public_cache
from desktop_assistant import Assistant, PhysicalInput
from desktop_updater import Updater, apply_update

if '--apply-update' in sys.argv:
    pos = sys.argv.index('--apply-update')
    apply_update(sys.argv[pos+1], sys.argv[pos+2])
    sys.exit(0)
if '--self-check' in sys.argv:
    import ssl
    context = ssl.create_default_context()
    print(json.dumps({'tls_ready':True,'hostname_verification':context.check_hostname,
                      'certificate_verification':context.verify_mode == ssl.CERT_REQUIRED}),flush=True)
    sys.exit(0)

ROOT = Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
CONFIG = json.loads((ROOT / 'local_config.json').read_text(encoding='utf-8-sig'))
PORT = CONFIG['port']
TOKEN = CONFIG['token']
ASSISTANT = Assistant(ROOT, physical=PhysicalInput())
UPDATER = Updater(ROOT, CONFIG)

def monitor_releases():
    while True:
        try:
            UPDATER.check()
        except Exception:
            pass
        ASSISTANT.update_required = UPDATER.status().get('required') is True
        time.sleep(1800)

ASSISTANT.update_required = UPDATER.status().get('required') is True
threading.Thread(target=monitor_releases, daemon=True).start()
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

def set_firewall(enabled):
    """Remove only legacy whole-process blocking rules; never create new ones."""
    if enabled:
        raise ValueError('Full-process blocking was removed; local mode only blocks rooms.')
    if not ctypes.windll.shell32.IsUserAnAdmin():
        result = powershell("$ErrorActionPreference='Stop';$r=@(Get-NetFirewallRule -PolicyStore ActiveStore -Name " + quote(PREFIX+'.*') + " -ErrorAction SilentlyContinue);if($r.Count -eq 0){'no_rules'}else{'rules_exist'}")
        if result.splitlines()[-1:] == ['no_rules']:
            return
        raise PermissionError('请通过启动器授予管理员权限，以清理旧版本的断网规则。')
    powershell("$ErrorActionPreference='Stop';Get-NetFirewallRule -Name " + quote(PREFIX+'.*') + " -ErrorAction SilentlyContinue|Remove-NetFirewallRule;exit 0;")

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
    def cached_asset(self, name):
        candidates=[ROOT/'cache/assets'/name]
        for previous in sorted(ROOT.glob('cache_previous_*'),reverse=True)[:2]:
            if previous.is_dir() and previous.resolve().is_relative_to(ROOT):
                candidates.append(previous/'assets'/name)
        for candidate in candidates:
            if candidate.is_file() and candidate.resolve().is_relative_to(ROOT):
                return candidate
        return None

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
                                      'mod_version': CONFIG.get('mod_version'), 'client_version': CONFIG.get('client_version'),
                                      'firewall_verified': False, 'mode_verified': True, 'network_policy': 'rooms-only',
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
                cached = self.cached_asset(name)
                if cached:
                    return self.respond(200, cached.read_bytes(), 'image/png')
        if path.startswith('/assets/'):
            name = path.removeprefix('/assets/')
            if '/' in name or '\\' in name or '..' in name:
                return self.respond(400, {'error': 'Invalid path'})
            p = self.cached_asset(name)
            if p:
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
        path = urlparse(self.path).path
        if path.startswith('/update/'):
            try:
                action = path.rsplit('/', 1)[-1]
                if action == 'check':
                    result = UPDATER.check()
                    ASSISTANT.update_required = result.get('required') is True
                    return self.respond(200, result)
                if action == 'status':
                    return self.respond(200, UPDATER.status())
                if action == 'healthy':
                    body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or b'{}')
                    return self.respond(200, UPDATER.healthy(body.get('version')))
                if action == 'install':
                    result = UPDATER.prepare()
                    ASSISTANT.handle('quit', {}, ACTUAL_OFFLINE)
                    self.respond(200, result)
                    def stop_for_update():
                        ASSISTANT.save(True)
                        self.server.shutdown()
                    threading.Timer(8, stop_for_update).start()
                    return
                return self.respond(404, {'error':'Unknown update action'})
            except Exception as error:
                return self.respond(409, {'error':str(error)})
        if path.startswith('/assistant/'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 16384:
                    raise ValueError('Request too large')
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError('Object required')
                return self.respond(200, ASSISTANT.handle(path.rsplit('/', 1)[-1], body, ACTUAL_OFFLINE))
            except Exception as error:
                return self.respond(400, {'error': str(error)})
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
                if enabled and not READY:
                    raise RuntimeError('离线素材缓存不完整，未开启。')
                set_firewall(False)
                ACTUAL_OFFLINE = enabled
                tmp = STATE.with_suffix('.tmp')
                tmp.write_text(json.dumps({'enabled': enabled}), encoding='utf-8')
                tmp.replace(STATE)
            return self.respond(200, {'enabled': enabled, 'firewall_verified': False, 'mode_verified': True, 'network_policy': 'rooms-only', 'ready': READY})
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
        set_firewall(False)
        ACTUAL_OFFLINE = True
    else:
        set_firewall(False)
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(json.dumps({'ready': READY, 'enabled': ACTUAL_OFFLINE, 'port': PORT}), flush=True)
    server.serve_forever()
    server.server_close()
    ASSISTANT.save(True)

if __name__ == '__main__':
    main()
