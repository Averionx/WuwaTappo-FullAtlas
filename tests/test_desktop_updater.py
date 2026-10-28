from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop_updater import FileTransaction, unpack, safe_name, validate_manifest, apply_update, Updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.contents={'WuwaTappo.Local.exe':b'new-pet','LocalGalleryHost.exe':b'new-host',
                       'package_config.json':b'{"mod_version":"1.1","client_version":"1.0.2"}'}
        self.manifest={'schema':1,'version':'1.1','files':[{'path':n,'size':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in self.contents.items()]}
    def tearDown(self):self.temp.cleanup()
    def archive(self,extra=None):
        path=self.root/'update.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('update_manifest.json',json.dumps(self.manifest))
            for n,v in self.contents.items():z.writestr(n,v)
            if extra:z.writestr(*extra)
        return path
    def test_transaction_preserves_data_and_rolls_back(self):
        target=self.root/'install';target.mkdir()
        for name in ['local_config.json','assistant_state.json','offline_state.json']:(target/name).write_text('private')
        (target/'profile').mkdir();(target/'profile/account').write_text('private-account')
        (target/'WuwaTappo.Local.exe').write_bytes(b'old-pet')
        stage=self.root/'job/stage';unpack(self.archive(),stage)
        t=FileTransaction(target,stage);t.apply()
        self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'new-pet')
        self.assertEqual((target/'profile/account').read_text(),'private-account')
        self.assertEqual((target/'local_config.json').read_text(),'private')
        t.rollback()
        self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'old-pet')
        self.assertFalse((target/'LocalGalleryHost.exe').exists())
        self.assertEqual((target/'assistant_state.json').read_text(),'private')
    def test_tampered_stage_never_changes_installation(self):
        target=self.root/'install';target.mkdir();(target/'WuwaTappo.Local.exe').write_bytes(b'old')
        stage=self.root/'job/stage';unpack(self.archive(),stage)
        (stage/'package_config.json').write_text('tamper')
        with self.assertRaises(ValueError):FileTransaction(target,stage).apply()
        self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'old')
    def test_invalid_zip_hash_and_extra_entries(self):
        with self.assertRaises(ValueError):unpack(self.archive(('profile/password',b'invalid')),self.root/'extra')
        self.contents['WuwaTappo.Local.exe']=b'fake'
        with self.assertRaises(ValueError):unpack(self.archive(),self.root/'hash')
    def test_data_paths_and_traversal_denied(self):
        for name in ['../a','/a','C:/a','_internal/../../x','profile/account','cache/atlas.json','local_config.json','assistant_state.json','runtime/msedgewebview2.exe','_internal/a:stream','_internal\\a']:
            with self.subTest(name=name),self.assertRaises(ValueError):safe_name(name)
    def test_duplicate_case_collision_denied(self):
        self.manifest['files'].append({**self.manifest['files'][0],'path':'WUWATAPPO.LOCAL.EXE'})
        with self.assertRaises(ValueError):validate_manifest(self.manifest)
    def test_api_quota_uses_public_release(self):
        updater=Updater(self.root,{'mod_version':'1.1'})
        with patch.object(updater,'fetch',side_effect=OSError('API quota')),patch.object(updater,'public_release',return_value={'tag_name':'v1.0','assets':[]}) as fallback:
            self.assertFalse(updater.check()['available'])
            fallback.assert_called_once()
    def release(self, draft=False, prerelease=False, complete=True):
        base='https://github.com/Averionx/WuwaTappo-FullAtlas/releases/download/v1.2/'
        name='WuwaTappo-FullAtlas-1.2-x64-update.zip'
        return {'tag_name':'v1.2','draft':draft,'prerelease':prerelease,'assets':[
            {'name':name,'browser_download_url':base+name,'size':1234},
            {'name':'SHA256SUMS.txt','browser_download_url':base+'SHA256SUMS.txt'}] if complete else []}
    def check_release(self,updater,release):
        sums=('a'*64+'  WuwaTappo-FullAtlas-1.2-x64-update.zip\n').encode()
        with patch.object(updater,'fetch',side_effect=[json.dumps(release).encode(),sums]):
            return updater.check()
    def test_formal_release_required_cached_and_survives_outage(self):
        updater=Updater(self.root,{'mod_version':'1.1'})
        self.assertTrue(self.check_release(updater,self.release())['required'])
        other=Updater(self.root,{'mod_version':'1.1'})
        self.assertTrue(other.status()['required'])
        with patch.object(other,'fetch',side_effect=OSError('offline')),patch.object(other,'public_release',side_effect=OSError('offline')):
            self.assertTrue(other.check()['required'])
        self.assertFalse(Updater(self.root,{'mod_version':'1.2'}).status()['required'])
    def test_draft_prerelease_incomplete_do_not_lock(self):
        for release in [self.release(draft=True),self.release(prerelease=True),self.release(complete=False)]:
            updater=Updater(self.root,{'mod_version':'1.1'})
            self.assertFalse(self.check_release(updater,release)['required'])
    def test_bad_checksum_never_creates_mandatory_policy(self):
        updater=Updater(self.root,{'mod_version':'1.1'})
        with patch.object(updater,'fetch',side_effect=[json.dumps(self.release()).encode(),b'invalid']):
            with self.assertRaises(ValueError):updater.check()
        self.assertFalse(updater.status()['required'])
    def test_frontend_health_must_match_package_version(self):
        updater=Updater(self.root,{'mod_version':'1.2'})
        with self.assertRaises(ValueError):updater.healthy('1.1')
        self.assertTrue(updater.healthy('1.2')['ok'])
    def test_invalid_later_release_cannot_clear_confirmed_requirement(self):
        updater=Updater(self.root,{'mod_version':'1.1'})
        self.check_release(updater,self.release())
        bad=self.release()
        bad['assets'][0]['browser_download_url']=bad['assets'][0]['browser_download_url'].replace('/v1.2/','/v9.9/')
        result=self.check_release(updater,bad)
        self.assertTrue(result['required'])
        self.assertEqual(result['version'],'1.2')
    def helper_fixture(self):
        target=self.root/'install';target.mkdir()
        (target/'WuwaTappo.Local.exe').write_bytes(b'old-pet')
        (target/'local_config.json').write_text('private')
        folder=target/'.updates/job';stage=folder/'stage'
        unpack(self.archive(),stage)
        (folder/'pending.json').write_text('{"version":"1.1"}')
        return target,folder,stage
    def test_helper_health_ack_cleans_backup(self):
        target,folder,stage=self.helper_fixture()
        with patch('desktop_updater.processes',return_value=[]),patch('desktop_updater.launch',side_effect=lambda root:(folder/'healthy').write_text('1.1')):
            apply_update(target,stage)
        self.assertTrue(json.loads((folder/'result.json').read_text())['ok'])
        self.assertFalse((folder/'backup').exists())
        self.assertFalse(stage.exists())
        self.assertEqual((target/'local_config.json').read_text(),'private')
    def test_helper_startup_timeout_restores_old_executable(self):
        target,folder,stage=self.helper_fixture()
        with patch('desktop_updater.processes',return_value=[]),patch('desktop_updater.launch') as launch,patch('psutil.wait_procs',return_value=([],[])),patch('desktop_updater.time.monotonic',side_effect=[0,0,91]):
            apply_update(target,stage)
        self.assertFalse(json.loads((folder/'result.json').read_text())['ok'])
        self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'old-pet')
        self.assertEqual(launch.call_count,2)
        self.assertEqual((target/'local_config.json').read_text(),'private')


if __name__=='__main__':unittest.main()
