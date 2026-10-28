from pathlib import Path
import json,os,shutil,subprocess,tempfile,unittest


@unittest.skipUnless(os.name=='nt','Windows launcher metadata')
class InitializeTests(unittest.TestCase):
    def test_upgrade_preserves_token_and_counts_synced_catalog(self):
        source=Path(__file__).resolve().parents[1]/'installer/initialize.ps1'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'cache').mkdir()
            (root/'initialize.ps1').write_text(source.read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
            (root/'package_config.json').write_text(json.dumps({'mod_version':'1.1','client_version':'1.0.2','asset_count':899,'atlas_count':899,'port':43229}))
            (root/'local_config.json').write_text(json.dumps({'token':'test-only','mod_version':'1.0','asset_count':2,'atlas_count':2}))
            (root/'cache/asset_manifest.json').write_text(json.dumps({'errors':[],'records':[1,2,3]}))
            (root/'cache/atlas.json').write_text(json.dumps({'data':[1,2]}))
            powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            result=subprocess.run([str(powershell),'-NoProfile','-File',str(root/'initialize.ps1')],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            config=json.loads((root/'local_config.json').read_text(encoding='utf-8-sig'))
            self.assertEqual(config['token'],'test-only')
            self.assertEqual(config['mod_version'],'1.1')
            self.assertEqual(config['asset_count'],3)
            self.assertEqual(config['atlas_count'],2)


if __name__=='__main__':unittest.main()
