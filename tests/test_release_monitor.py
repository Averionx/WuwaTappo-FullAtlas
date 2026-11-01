"""Execute the real host loop without importing the live service or credentials."""
from pathlib import Path
from types import SimpleNamespace
import ast
import unittest


class MonitorTests(unittest.TestCase):
    def test_checks_immediately_then_every_thirty_minutes_and_updates_lock(self):
        source=(Path(__file__).resolve().parents[1]/'src/local_host.py').read_text(encoding='utf-8')
        function=next(node for node in ast.parse(source).body if isinstance(node,ast.FunctionDef) and node.name=='monitor_releases')
        events=[]
        class StopTest(Exception):pass
        def check():events.append('check')
        def sleep(seconds):
            events.append(('sleep',seconds))
            if events.count('check')==2:raise StopTest()
        assistant=SimpleNamespace(update_required=False)
        values=iter([True,False])
        def status():return {'required':next(values)}
        namespace={'UPDATER':SimpleNamespace(check=check,status=status),'ASSISTANT':assistant,'time':SimpleNamespace(sleep=sleep)}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'release-monitor','exec'),namespace)
        with self.assertRaises(StopTest):namespace['monitor_releases']()
        self.assertEqual(events,['check',('sleep',1800),'check',('sleep',1800)])
        self.assertFalse(assistant.update_required)


if __name__=='__main__':unittest.main()
