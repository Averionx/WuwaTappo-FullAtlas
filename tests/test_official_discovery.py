from pathlib import Path
import sys,tempfile,unittest,json
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop_updater import Updater

class OfficialDiscoveryTests(unittest.TestCase):
    def test_follows_official_indirection_and_preserves_cache_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Updater,'check_official'):
                updater=Updater(Path(directory),{'mod_version':'1.3.7','client_version':'1.0.4'})
            target='https://mc-wuwatappo.kurogames-global.com/app/version-json/latest.json?t=123'
            with patch.object(updater,'fetch',side_effect=[json.dumps({'url':target}).encode(),json.dumps({'version':'1.0.5'}).encode()]) as fetch:
                Updater.check_official(updater)
            self.assertIn('/app/json-host/latest_host.json?',fetch.call_args_list[0].args[0])
            self.assertEqual(fetch.call_args_list[1].args[0],target)
            self.assertEqual(updater.official_version,'1.0.5')
            self.assertTrue(updater.waiting_for_adapter)

    def test_rejects_foreign_manifest_host(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Updater,'check_official'):
                updater=Updater(Path(directory),{'mod_version':'1.3.7','client_version':'1.0.4'})
            with patch.object(updater,'fetch',return_value=b'{"url":"https://example.com/app/version-json/latest.json"}'):
                with self.assertRaises(ValueError):Updater.check_official(updater)
