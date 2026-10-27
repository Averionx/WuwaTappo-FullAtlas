"""Refresh public catalog data; commit only after all referenced images verify."""
from pathlib import Path
import concurrent.futures, hashlib, json, os, shutil, time, urllib.parse, urllib.request

API = 'https://api-mc-wuwatappo.kurogames-global.com'

def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'WuwaTappo-LocalGallery-Cache'}), timeout=30) as response:
        return json.load(response)

def sync(root, progress):
    root = Path(root)
    cache = root / 'cache'
    activity = get_json(API + '/api/common/activity-config')
    atlas = get_json(API + '/api/common/atlas')
    if activity.get('code') != 0 or atlas.get('code') != 0 or not isinstance(atlas.get('data'), list) or not atlas['data']:
        raise ValueError('官方目录响应格式异常，保留原缓存')
    host = activity['data']['assets_host'].rstrip('/')
    if urllib.parse.urlparse(host).hostname not in ['mc-wuwatappo.kurogames-global.com']:
        raise ValueError('未识别的素材域名，保留原缓存')
    old_atlas = json.loads((cache / 'atlas.json').read_text(encoding='utf-8'))
    old_activity = json.loads((cache / 'activity-config.json').read_text(encoding='utf-8'))
    if old_activity['data'].get('assets_json_ts') == activity['data'].get('assets_json_ts') and old_atlas['data'] == atlas['data']:
        return {'changed': False, 'atlas_count': len(atlas['data']), 'asset_count': len(json.loads((cache / 'asset_manifest.json').read_text())['records'])}
    pointer = get_json(host + '/app/json-host/appearance_asset_host.json')
    url = pointer['url']
    if urllib.parse.urlparse(url).hostname != urllib.parse.urlparse(host).hostname:
        raise ValueError('未识别的素材清单地址')
    catalog = get_json(url)
    types = ['character_skin', 'accessory', 'emote']
    if not all(isinstance(catalog.get(t), dict) and isinstance(catalog.get(t + '_atlas'), dict) for t in types):
        raise ValueError('新版素材结构不兼容，保留原缓存')
    for item in atlas['data']:
        typ = item['asset_type']
        entry = catalog[typ].get(str(item['asset_id']))
        if not entry or str(entry.get('height_light_id')) not in catalog[typ.removesuffix('_atlas')]:
            raise ValueError('图鉴到可用外观的映射缺失，保留原缓存')
    stage = root / ('cache_staging_' + str(time.time_ns()))
    assets = stage / 'assets'
    assets.mkdir(parents=True)
    jobs = {}
    def rewrite(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == 'url' and isinstance(value, str):
                    full = urllib.parse.urljoin(host + '/', value)
                    if urllib.parse.urlparse(full).hostname != urllib.parse.urlparse(host).hostname:
                        raise ValueError('未识别的外部图片域名')
                    name = hashlib.sha256(full.encode()).hexdigest() + '.png'
                    jobs[name] = full
                    obj[key] = 'assets/' + name
                else:
                    rewrite(value)
        elif isinstance(obj, list):
            for value in obj:
                rewrite(value)
    rewrite(catalog)
    def download(pair):
        name, source = pair
        target = assets / name
        existing = cache / 'assets' / name
        if existing.exists():
            try:
                os.link(existing, target)
            except OSError:
                shutil.copy2(existing, target)
            data = target.read_bytes()
        else:
            error = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(source, timeout=40) as response:
                        data = response.read()
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    time.sleep(attempt + 0.5)
            if error:
                raise error
            target.write_bytes(data)
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('下载素材不是有效 PNG')
        return {'file': name, 'source': source, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(download, item) for item in jobs.items()]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            records.append(future.result())
            progress(i, len(jobs))
    for name, obj in [('activity-config.json', activity), ('atlas.json', atlas), ('offline_catalog.json', catalog),
                      ('asset_manifest.json', {'records': records, 'errors': []})]:
        (stage / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    # Preserve a recoverable previous generation; never replace a working cache
    # with a partial download. The host serializes this with mode changes.
    archive = root / ('cache_previous_' + str(time.time_ns()))
    cache.rename(archive)
    try:
        stage.rename(cache)
    except Exception:
        archive.rename(cache)
        raise
    return {'changed': True, 'atlas_count': len(atlas['data']), 'asset_count': len(records),
            'assets_json_ts': activity['data']['assets_json_ts']}
