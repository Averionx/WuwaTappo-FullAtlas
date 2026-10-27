import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pathlib import Path
import hashlib, io, json, tempfile, unittest
from unittest.mock import patch
import sync_cache

class CacheSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        (self.cache / 'assets').mkdir(parents=True)
        self.host = 'https://mc-wuwatappo.kurogames-global.com'
        self.old_atlas = {'code': 0, 'data': []}
        self.old_activity = {'code': 0, 'data': {'assets_host': self.host, 'assets_json_ts': 1}}
        for name, obj in [('atlas.json', self.old_atlas), ('activity-config.json', self.old_activity), ('asset_manifest.json', {'records': [], 'errors': []})]:
            (self.cache / name).write_text(json.dumps(obj), encoding='utf-8')
        self.atlas = {'code': 0, 'data': [{'asset_id': 2, 'asset_name': 'role_test.png', 'asset_type': 'character_skin_atlas'}]}
        self.activity = {'code': 0, 'data': {'assets_host': self.host, 'assets_json_ts': 2}}
        self.catalog = {'character_skin': {'1': {'url': 'character.png', 'body1': {'url': 'body.png'}}},
            'character_skin_atlas': {'2': {'url': 'atlas.png', 'height_light_id': 1}},
            'accessory': {}, 'accessory_atlas': {}, 'emote': {}, 'emote_atlas': {}}
        import base64
        self.png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6X2kAAAAASUVORK5CYII=')

    def tearDown(self):
        self.temp.cleanup()

    def get_json(self, url):
        if url.endswith('/activity-config'): return json.loads(json.dumps(self.activity))
        if url.endswith('/atlas'): return json.loads(json.dumps(self.atlas))
        if url.endswith('/appearance_asset_host.json'): return {'url': self.host + '/appearance_asset.json'}
        return json.loads(json.dumps(self.catalog))

    def test_new_catalog_commits_complete_verified_cache(self):
        progress = []
        with patch.object(sync_cache, 'get_json', side_effect=self.get_json), patch.object(sync_cache.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(self.png)):
            result = sync_cache.sync(self.root, lambda done, total: progress.append((done, total)))
        self.assertEqual(result, {'changed': True, 'atlas_count': 1, 'asset_count': 3, 'assets_json_ts': 2})
        self.assertEqual(progress[-1], (3, 3))
        manifest = json.loads((self.cache / 'asset_manifest.json').read_text())
        for item in manifest['records']:
            self.assertEqual(hashlib.sha256((self.cache / 'assets' / item['file']).read_bytes()).hexdigest(), item['sha256'])
        self.assertEqual(len(list(self.root.glob('cache_previous_*'))), 1)

    def test_failed_image_download_keeps_previous_cache(self):
        before = (self.cache / 'atlas.json').read_bytes()
        with patch.object(sync_cache, 'get_json', side_effect=self.get_json), patch.object(sync_cache.urllib.request, 'urlopen', side_effect=OSError('network failure')), patch.object(sync_cache.time, 'sleep'):
            with self.assertRaises(OSError): sync_cache.sync(self.root, lambda *args: None)
        self.assertEqual((self.cache / 'atlas.json').read_bytes(), before)
        self.assertFalse(list(self.root.glob('cache_previous_*')))

    def test_missing_id_mapping_never_commits(self):
        self.catalog['character_skin_atlas']['2']['height_light_id'] = 999
        with patch.object(sync_cache, 'get_json', side_effect=self.get_json):
            with self.assertRaisesRegex(ValueError, '映射缺失'): sync_cache.sync(self.root, lambda *args: None)
        self.assertEqual(json.loads((self.cache / 'atlas.json').read_text()), self.old_atlas)

    def test_unchanged_version_downloads_no_images(self):
        self.activity = self.old_activity
        self.atlas = self.old_atlas
        self.atlas['data'] = [{'asset_id': 2}]
        (self.cache / 'atlas.json').write_text(json.dumps(self.atlas), encoding='utf-8')
        with patch.object(sync_cache, 'get_json', side_effect=self.get_json), patch.object(sync_cache.urllib.request, 'urlopen') as download:
            result = sync_cache.sync(self.root, lambda *args: None)
        self.assertFalse(result['changed'])
        download.assert_not_called()

if __name__ == '__main__':
    unittest.main(verbosity=2)
