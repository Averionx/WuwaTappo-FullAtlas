from pathlib import Path
import sys,os,unittest
from contextlib import contextmanager
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from process_launch import popen_independent,clean_dll_search_path


class Fn:
    def __init__(self,call):self.call=call
    def __call__(self,*args):return self.call(*args)


class LaunchTests(unittest.TestCase):
    def test_independent_frozen_child_without_parent_env_mutation(self):
        state={'clean':False}
        @contextmanager
        def clean():
            state['clean']=True
            try:yield
            finally:state['clean']=False
        def spawn(args,**kwargs):
            self.assertTrue(state['clean']);self.assertEqual(kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
            return 'child'
        with patch.dict(os.environ,{'PYINSTALLER_RESET_ENVIRONMENT':'0'}),patch('process_launch.clean_dll_search_path',clean),patch('process_launch.subprocess.Popen',side_effect=spawn):
            self.assertEqual(popen_independent(['app.exe']),'child')
            self.assertEqual(os.environ['PYINSTALLER_RESET_ENVIRONMENT'],'0')
            self.assertFalse(state['clean'])
    def test_dll_directory_is_restored_even_on_launch_error(self):
        saved=r'C:\Temp\_MEI-example';calls=[]
        def get(size,buffer):
            if buffer is not None:buffer.value=saved
            return len(saved)+1
        fake=SimpleNamespace(GetDllDirectoryW=Fn(get),SetDllDirectoryW=Fn(lambda path:calls.append(path) or True))
        with patch('process_launch.ctypes.WinDLL',return_value=fake):
            with self.assertRaises(RuntimeError):
                with clean_dll_search_path():raise RuntimeError('test child failed')
        self.assertEqual(calls,[None,saved])


if __name__=='__main__':unittest.main()
