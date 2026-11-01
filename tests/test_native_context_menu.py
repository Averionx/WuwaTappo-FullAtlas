from pathlib import Path
import ctypes
from ctypes import wintypes
import sys,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from native_context_menu import WindowsPopup,popup,validate_items


class FakeAPI:
    def __init__(self,selection=1):self.selection=selection;self.foreground=7;self.events=[];self.handle=100
    def CreatePopupMenu(self):self.handle+=1;return self.handle
    def AppendMenuW(self,*args):self.events.append(('append',args));return True
    def GetForegroundWindow(self):return self.foreground
    def SetForegroundWindow(self,owner):self.foreground=owner;self.events.append(('foreground',owner));return True
    def CreateWindowExW(self,*args):return 500
    def ShowWindow(self,*args):return True
    def GetCursorPos(self,value):
        point=ctypes.cast(value,ctypes.POINTER(wintypes.POINT)).contents;point.x=100;point.y=200;return True
    def TrackPopupMenuEx(self,*args):self.events.append(('track',args));return self.selection
    def PostMessageW(self,*args):return True
    def DestroyWindow(self,owner):self.events.append(('destroy-window',owner));return True
    def DestroyMenu(self,menu):self.events.append(('destroy-menu',menu));return True


class NativeMenuTests(unittest.TestCase):
    def model(self):return validate_items([{'key':'console','text':'控制台'},{'key':'setting','text':'设置'}])
    def instance(self,api):
        instance=WindowsPopup.__new__(WindowsPopup);instance.api=api;return instance
    def test_console_selection_and_cleanup_without_cursor_writes(self):
        api=FakeAPI();self.assertEqual(self.instance(api).show(self.model()),'console')
        self.assertIn(('destroy-window',500),api.events);self.assertIn(('destroy-menu',101),api.events)
        track=next(args for event,args in api.events if event=='track');self.assertEqual(track[2:4],(100,200));self.assertTrue(track[1]&0x100)
    def test_cancel_does_not_steal_new_foreground(self):
        api=FakeAPI(0)
        def cancel(*args):api.foreground=999;return 0
        api.TrackPopupMenuEx=cancel
        self.assertIsNone(self.instance(api).show(self.model()))
        self.assertEqual(api.foreground,999);self.assertIn(('destroy-window',500),api.events)
    def test_tracking_error_always_releases_owner_and_menu(self):
        api=FakeAPI()
        def fail(*_):raise OSError('tracking failed')
        api.TrackPopupMenuEx=fail
        with self.assertRaises(OSError):self.instance(api).show(self.model())
        self.assertIn(('destroy-menu',101),api.events);self.assertIn(('destroy-window',500),api.events)
    def test_validation_does_not_allow_arbitrary_commands_or_deep_submenus(self):
        for items in [[{'key':'execute-shell','text':'x'}],[{'key':'console','text':'x\ny'}],[{'text':'x','items':[{'text':'y','items':[{'key':'console','text':'z'}]}]}]]:
            with self.assertRaises(ValueError):validate_items(items)
    def test_second_popup_does_not_capture_another_menu(self):
        entered=threading.Event();release=threading.Event()
        class Blocking:
            def show(self,items):entered.set();release.wait(2);return 'console'
        result=[];thread=threading.Thread(target=lambda:result.append(popup(self.model(),implementation=Blocking())))
        thread.start();self.assertTrue(entered.wait(1));self.assertTrue(popup(self.model(),implementation=Blocking())['busy']);release.set();thread.join(2)
        self.assertEqual(result,[{'action':'console'}])

if __name__=='__main__':unittest.main()
