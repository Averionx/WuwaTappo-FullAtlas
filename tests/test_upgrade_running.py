from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,sys,tempfile,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop_updater import request_graceful_exit,apply_update
import test_desktop_updater as fixtures


class RunningUpgradeTests(unittest.TestCase):
    def test_requests_existing_apps_authenticated_quit_endpoint(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path,self.headers.get('X-Local-Token'),self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}')
            def log_message(self,*_):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'local_config.json').write_text(json.dumps({'port':server.server_port,'token':'test-only'}))
                self.assertTrue(request_graceful_exit(root))
                self.assertEqual(received,[('/assistant/quit','test-only',b'{}')])
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_running_app_is_saved_and_exited_before_replacing_bytes(self):
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            root,folder,stage=fixture.helper_fixture();running=True
            def exit_app(target):
                nonlocal running
                self.assertEqual((target/'WuwaTappo.Local.exe').read_bytes(),b'old-pet');running=False;return True
            native=SimpleNamespace(exe=lambda:str(root/'WuwaTappo.Local.exe'))
            with patch('desktop_updater.request_graceful_exit',side_effect=exit_app) as quit_app,patch('desktop_updater.processes',side_effect=lambda root:[native] if running else []),patch('desktop_updater.launch',side_effect=lambda root,job:(folder/'healthy').write_text('1.1')):
                apply_update(root,stage)
            quit_app.assert_called_once_with(root)
            self.assertTrue(json.loads((folder/'result.json').read_text())['ok'])
            self.assertEqual((root/'local_config.json').read_text(),'private')
        finally:fixture.tearDown()

    def test_unresponsive_open_app_is_not_killed_or_relaunched(self):
        fixture=fixtures.UpdaterTests();fixture.setUp()
        try:
            root,folder,stage=fixture.helper_fixture();now=[0]
            def wait(_):now[0]=100
            native=SimpleNamespace(exe=lambda:str(root/'WuwaTappo.Local.exe'),terminate=lambda:self.fail('must not kill unsaved original app'))
            with patch('desktop_updater.request_graceful_exit',return_value=False),patch('desktop_updater.processes',return_value=[native]),patch('process_lifecycle.native_is_running',return_value=True),patch('desktop_updater.launch') as launch,patch('desktop_updater.time.monotonic',side_effect=lambda:now[0]),patch('desktop_updater.time.sleep',side_effect=wait):
                apply_update(root,stage)
            launch.assert_not_called();self.assertFalse(json.loads((folder/'result.json').read_text())['ok'])
            self.assertEqual((root/'WuwaTappo.Local.exe').read_bytes(),b'old-pet')
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
