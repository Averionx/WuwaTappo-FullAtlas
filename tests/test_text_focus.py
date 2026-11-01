import sys,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from text_focus import FocusedTextProbe


class Element:
    def __init__(self,typ,readonly=False,value=False,text_edit=False):
        self.CurrentControlType=typ
        self.props={30046:readonly,30043:value,30149:text_edit}
    def GetCurrentPropertyValue(self,key):
        # Any attempt to read text/name/value or other properties fails the test.
        return self.props[key]


class TextFocusTests(unittest.TestCase):
    def probe(self,element):
        class UIA:
            def GetFocusedElement(self):return element
        with patch('comtypes.client.CreateObject',return_value=UIA()):
            return FocusedTextProbe().probe(2)['editable']
    def test_modern_edit(self):self.assertTrue(self.probe(Element(50004)))
    def test_readonly_edit(self):self.assertFalse(self.probe(Element(50004,readonly=True)))
    def test_editable_document(self):self.assertTrue(self.probe(Element(50030,text_edit=True)))
    def test_reading_document(self):self.assertFalse(self.probe(Element(50030)))
    def test_game_pane(self):self.assertFalse(self.probe(Element(50033)))
    def test_slow_provider_is_bounded_and_single_flight(self):
        gate=threading.Event();entered=threading.Event()
        class UIA:
            def GetFocusedElement(self):
                entered.set();gate.wait(2);return Element(50004)
        with patch('comtypes.client.CreateObject',return_value=UIA()):
            probe=FocusedTextProbe();start=time.monotonic()
            result=probe.probe(.03);self.assertFalse(result['editable'])
            self.assertLess(time.monotonic()-start,.5)
            self.assertTrue(entered.wait(1));self.assertEqual(probe.probe()['source'],'uia-busy')
            gate.set()
            for _ in range(50):
                if not probe.busy:break
                time.sleep(.01)
            self.assertFalse(probe.busy)


if __name__=='__main__':unittest.main()
