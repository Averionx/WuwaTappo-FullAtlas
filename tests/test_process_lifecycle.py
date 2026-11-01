from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from process_lifecycle import native_is_running,watch_native_exit


class LifecycleTests(unittest.TestCase):
    def test_only_exact_installation_is_considered_running(self):
        root=Path('test-install').resolve()
        def process(name,exe):return SimpleNamespace(info={'name':name,'exe':exe})
        with patch('psutil.process_iter',return_value=[process('WuwaTappo.Local.exe',str(root/'WuwaTappo.Local.exe'))]):self.assertIs(native_is_running(root),True)
        with patch('psutil.process_iter',return_value=[process('WuwaTappo.Local.exe',str(root.parent/'another/WuwaTappo.Local.exe'))]):self.assertIs(native_is_running(root),False)
        with patch('psutil.process_iter',return_value=[process('WuwaTappo.Local.exe',None)]):self.assertIsNone(native_is_running(root))
    def watch(self,sequence,grace=2):
        event=threading.Event();state={'time':0,'calls':0,'stopped':False}
        def scan(root):
            index=state['calls'];state['calls']+=1
            return sequence[min(index,len(sequence)-1)]
        def wait(seconds):
            state['time']+=seconds
            if state['calls']>=len(sequence):event.set()
        def stop():state['stopped']=True
        watch_native_exit(Path('test-install'),stop,stop_event=event,scan=scan,wait=wait,clock=lambda:state['time'],grace=grace)
        return state
    def test_host_can_start_before_native_pet(self):
        self.assertFalse(self.watch([False,False,False])['stopped'])
    def test_native_exit_retires_host_after_grace(self):
        s=self.watch([True,False,False,False])
        self.assertTrue(s['stopped']);self.assertEqual(s['time'],3)
    def test_unknown_permissions_or_reappearing_pet_cancel_retirement(self):
        self.assertFalse(self.watch([True,False,None,False,False])['stopped'])
        self.assertFalse(self.watch([True,False,False,True,False])['stopped'])
