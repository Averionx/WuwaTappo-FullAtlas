from pathlib import Path
import io
import hashlib
import json
import sys
import tempfile
import threading
import time
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop_updater import Updater,FileTransaction,apply_update
from update_progress import UpdateLease,read_progress,write_progress
import test_desktop_updater as fixtures


class InstallTests(unittest.TestCase):
    def test_standalone_upgrade_registers_one_active_job(self):
        import upgrade_bootstrap
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            root=fixture.root/'install';root.mkdir()
            for name in ('WuwaTappo.Local.exe','LocalGalleryHost.exe','launch.ps1'):(root/name).write_bytes(b'old')
            (root/'local_config.json').write_text('{"mod_version":"1.0"}')
            payload=fixture.root/'payload';payload.mkdir();__import__('shutil').copy2(fixture.archive(),payload/'upgrade-payload.zip')
            with patch.object(sys,'argv',['Upgrade.exe','--target',str(root)]),patch.object(sys,'_MEIPASS',str(payload),create=True),patch.object(upgrade_bootstrap,'popen_independent',return_value=SimpleNamespace(pid=os.getpid())) as launch:
                upgrade_bootstrap.main();first=read_progress(root);upgrade_bootstrap.main()
            self.assertEqual(launch.call_count,1)
            self.assertEqual(first['version'],'1.1');self.assertEqual(first['phase'],'queued');self.assertEqual(first['pid'],os.getpid())
        finally:fixture.tearDown()

    def test_helper_waits_for_its_bootstrap_lease_handoff(self):
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            root=fixture.root/'install';root.mkdir();(root/'WuwaTappo.Local.exe').write_bytes(b'old-pet')
            folder=root/'.updates'/('b'*32);stage=folder/'stage';folder.mkdir(parents=True)
            fixtures.unpack(fixture.archive(),stage)
            (folder/'pending.json').write_text('{"version":"1.1"}')
            (folder.parent/'install-current.json').write_text(json.dumps({'job':folder.name,'version':'1.1'}))
            write_progress(folder,'queued',70,'ready')
            entered=threading.Event()
            def bootstrap():
                with UpdateLease(root):entered.set();time.sleep(.15)
            owner=threading.Thread(target=bootstrap);owner.start();self.assertTrue(entered.wait(2))
            with patch('desktop_updater.processes',return_value=[]),patch('desktop_updater.launch',side_effect=lambda root,job:(folder/'healthy').write_text('1.1')):
                apply_update(root,stage)
            owner.join(2);self.assertTrue(json.loads((folder/'result.json').read_text())['ok'])
            self.assertEqual((root/'WuwaTappo.Local.exe').read_bytes(),b'new-pet')
        finally:fixture.tearDown()

    def test_finished_result_overrides_stale_in_progress_display(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);job='a'*32;folder=root/'.updates'/job;folder.mkdir(parents=True)
            (folder.parent/'install-current.json').write_text(json.dumps({'job':job,'version':'1.1'}))
            write_progress(folder,'installing',80,'旧显示')
            (folder/'result.json').write_text('{"ok":false,"error":"test failure"}')
            self.assertEqual(read_progress(root)['phase'],'failed')

    def test_progress_reader_lock_does_not_abort_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);replace=__import__('os').replace;attempts=[]
            def locked_once(source,target):
                attempts.append(source)
                if len(attempts)==1:raise PermissionError('UI reader still open')
                return replace(source,target)
            with patch('update_progress.os.replace',side_effect=locked_once),patch('update_progress.time.sleep'):
                write_progress(root,'installing',90,'正在替换文件…')
            self.assertEqual(json.loads((root/'progress.json').read_text(encoding='utf-8'))['percent'],90)
            self.assertEqual(len(attempts),2)
            self.assertEqual(list(root.glob('*.tmp')),[])

    def test_repeated_install_requests_keep_one_worker_and_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);updater=Updater(root,{'mod_version':'1.0'})
            updater.available={'version':'1.1'}
            entered=threading.Event();release=threading.Event();done=threading.Event()
            def prepare(folder):entered.set();release.wait(3);return {'restarting':True}
            with patch.object(updater,'prepare',side_effect=prepare) as worker:
                first=updater.start_install(lambda _:done.set());self.assertTrue(entered.wait(2))
                second=updater.start_install(lambda _:self.fail('duplicate callback'))
                self.assertEqual(first['installation']['job'],second['installation']['job'])
                self.assertEqual(worker.call_count,1)
                release.set();self.assertTrue(done.wait(2))

    def test_native_busy_file_is_retried_without_second_update(self):
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            target,folder,stage=fixture.helper_fixture();real_replace=__import__('os').replace
            blocked=[];progress=[]
            def replace(source,destination):
                if Path(destination)==target/'WuwaTappo.Local.exe' and not blocked:
                    blocked.append(True);raise PermissionError('old executable still closing')
                return real_replace(source,destination)
            with patch('desktop_updater.os.replace',side_effect=replace),patch('desktop_updater.time.sleep'):
                FileTransaction(target,stage).apply(lambda percent,message:progress.append((percent,message)))
            self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'new-pet')
            self.assertTrue(any('等待旧文件' in message for _,message in progress))
            self.assertEqual(progress[-1][0],96)
        finally:fixture.tearDown()

    def test_second_helper_cannot_touch_files_or_restart_during_transaction(self):
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            target,folder,stage=fixture.helper_fixture()
            with UpdateLease(target),patch('desktop_updater.launch') as launch:
                apply_update(target,stage)
                launch.assert_not_called()
            self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'old-pet')
            self.assertFalse(json.loads((folder/'result.json').read_text())['ok'])
        finally:fixture.tearDown()

    def test_streaming_download_records_real_bytes_and_stages_once(self):
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            archive=fixture.archive().read_bytes();root=fixture.root
            (root/'LocalGalleryHost.exe').write_bytes(b'host');(root/'_internal').mkdir()
            updater=Updater(root,{'mod_version':'1.0'})
            updater.available={'version':'1.1','url':'https://github.com/Averionx/WuwaTappo-FullAtlas/releases/download/v1.1/test.zip','size':len(archive),'sha256':hashlib.sha256(archive).hexdigest()}
            phases=[]
            def record(folder,phase,percent,message,**extra):
                phases.append((phase,percent,extra));return write_progress(folder,phase,percent,message,**extra)
            with patch('desktop_updater.urllib.request.urlopen',return_value=io.BytesIO(archive)),patch('desktop_updater.popen_independent') as launch,patch('desktop_updater.write_progress',side_effect=record):
                result=updater.prepare()
            self.assertTrue(result['restarting']);self.assertEqual(launch.call_count,1)
            downloaded=[row for row in phases if row[0]=='downloading'][-1]
            self.assertEqual(downloaded[2]['completed'],len(archive));self.assertEqual(downloaded[2]['total'],len(archive))
            self.assertIn('verifying',[row[0] for row in phases]);self.assertIn('extracting',[row[0] for row in phases])
        finally:fixture.tearDown()

    def test_failed_health_does_not_acknowledge_old_failed_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);job=root/'.updates/failed';job.mkdir(parents=True)
            (job/'pending.json').write_text('{"version":"1.1"}')
            (job/'result.json').write_text('{"ok":false}')
            Updater(root,{'mod_version':'1.1'}).healthy('1.1')
            self.assertFalse((job/'healthy').exists())

if __name__=='__main__':unittest.main()
