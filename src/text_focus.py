"""Bounded read-only UIA focus probe for Chromium, chat apps and modern editors.

Never retrieves Name, Value, text ranges or keyboard content. One daemon worker
isolates slow accessibility providers from the assistant's tick/exit lifecycle.
"""
import threading


class FocusedTextProbe:
    def __init__(self):
        self.lock=threading.Lock()
        self.busy=False

    def probe(self, timeout=.3):
        with self.lock:
            if self.busy:return {'editable':False,'source':'uia-busy'}
            self.busy=True
        done=threading.Event();result={'editable':False,'source':'uia-timeout'}
        def work():
            initialized=False
            automation=element=None
            try:
                import sys
                sys.coinit_flags=0
                import comtypes
                from comtypes.client import CreateObject
                from comtypes.gen.UIAutomationClient import IUIAutomation
                comtypes.CoInitializeEx(0);initialized=True
                automation=CreateObject('{FF48DBA4-60EF-4201-AA87-54103EEF594E}',interface=IUIAutomation)
                element=automation.GetFocusedElement()
                typ=element.CurrentControlType
                readonly=element.GetCurrentPropertyValue(30046)
                value_pattern=element.GetCurrentPropertyValue(30043)
                text_edit=element.GetCurrentPropertyValue(30149)
                editable=(readonly is not True and (typ==50004 or typ==50003 and value_pattern is True or typ==50030 and text_edit is True))
                result.update(editable=bool(editable),source='uia',control_type=typ)
            except Exception:
                result.update(editable=False,source='uia-unavailable')
            finally:
                element=automation=None
                if initialized:comtypes.CoUninitialize()
                with self.lock:self.busy=False
                done.set()
        threading.Thread(target=work,name='text-focus-probe',daemon=True).start()
        return dict(result) if done.wait(timeout) else {'editable':False,'source':'uia-timeout'}
