from pathlib import Path
import hashlib,json,sys,tempfile,unittest,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from portable_bootstrap import CRITICAL,prepare,read_manifest,safe_path,within,already_running
from unittest.mock import patch


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.files={n:('public '+n).encode() for n in CRITICAL}
        self.files.update({'package_config.json':b'{"mod_version":"1.3.4"}', 'initialize.ps1':b'public init'})
        self.manifest={'schema':1,'version':'1.3.4','files':[{'path':n,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in self.files.items()]}
    def tearDown(self):self.temp.cleanup()
    def archive(self,extra=None):
        path=self.root/'bundle.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('portable_manifest.json',json.dumps(self.manifest))
            for name,data in self.files.items():z.writestr(name,data)
            if extra:z.writestr(*extra)
        return path
    def test_first_prepare_and_relaunch_preserve_user_data(self):
        target=self.root/'portable'
        self.assertEqual(prepare(self.archive(),target),'prepared')
        for name in ['local_config.json','offline_state.json','assistant_state.json']:(target/name).write_text('private')
        (target/'profile').mkdir();(target/'profile/account').write_text('private account')
        self.assertEqual(prepare(self.archive(),target),'ready')
        for name in ['local_config.json','offline_state.json','assistant_state.json']:self.assertEqual((target/name).read_text(),'private')
        self.assertEqual((target/'profile/account').read_text(),'private account')
    def test_old_outer_launcher_never_downgrades_in_app_upgrade(self):
        target=self.root/'portable';prepare(self.archive(),target)
        (target/'package_config.json').write_text('{"mod_version":"1.4"}')
        (target/'WuwaTappo.Local.exe').write_bytes(b'newer executable')
        self.assertEqual(prepare(self.archive(),target),'newer-installed')
        self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'newer executable')
    def test_existing_updated_cache_is_not_replaced(self):
        target=self.root/'portable';target.mkdir();(target/'cache').mkdir();(target/'cache/atlas.json').write_text('newer catalog')
        prepare(self.archive(),target)
        self.assertEqual((target/'cache/atlas.json').read_text(),'newer catalog')
    def test_bad_hash_does_not_replace_existing_file(self):
        target=self.root/'portable';target.mkdir();(target/'WuwaTappo.Local.exe').write_bytes(b'old good')
        self.files['WuwaTappo.Local.exe']=b'x'*len(self.files['WuwaTappo.Local.exe'])
        with self.assertRaises(ValueError):prepare(self.archive(),target)
        self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'old good')
        self.assertFalse((target/'portable_ready.json').exists())
    def test_private_and_traversal_paths_are_rejected(self):
        for path in ['local_config.json','profile/account','assistant_state.json','../outside','cache/../../outside','cache\\escape','cache/a:stream','/cache/absolute','C:/a']:
            with self.subTest(path=path),self.assertRaises(ValueError):safe_path(path)
    def test_manifest_extra_file_rejected(self):
        with zipfile.ZipFile(self.archive(('profile/account',b'secret'))) as z:
            with self.assertRaises(ValueError):read_manifest(z)
    def test_missing_runtime_rejected(self):
        del self.files['runtime/msedgewebview2.exe']
        self.manifest['files']=[r for r in self.manifest['files'] if r['path']!='runtime/msedgewebview2.exe']
        with zipfile.ZipFile(self.archive()) as z:
            with self.assertRaises(ValueError):read_manifest(z)
    def test_launcher_waits_for_just_closed_host_to_release_port(self):
        probes=iter([True,True,False]);waits=[]
        with patch('portable_bootstrap.native_is_running',return_value=False):
            self.assertFalse(already_running(self.root,probe=lambda:next(probes),clock=lambda:0,wait=waits.append))
        self.assertEqual(len(waits),1)
    def test_launcher_does_not_stop_another_active_copy(self):
        now=[0]
        def wait(seconds):now[0]+=seconds
        with patch('portable_bootstrap.native_is_running',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'另一份全图鉴版'):
                already_running(self.root,probe=lambda:True,clock=lambda:now[0],wait=wait)
    def test_link_outside_root_rejected(self):
        target=self.root/'portable';target.mkdir();outside=self.root/'outside';outside.mkdir()
        try:(target/'cache').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('OS does not grant symbolic-link creation')
        with self.assertRaises(ValueError):within(target,'cache/atlas.json')


if __name__=='__main__':unittest.main()
