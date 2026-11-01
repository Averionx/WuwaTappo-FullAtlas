from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import base64
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from startup_manager import StartupManager


class StartupTests(unittest.TestCase):
    def test_script_targets_launcher_in_interactive_user_session(self):
        manager=StartupManager(Path("test folder's pet"))
        script=manager.script('enable')
        self.assertIn("-File \"'+$taskLauncher+'\"'",script)
        self.assertIn('-WorkingDirectory $taskRoot',script)
        self.assertIn('-LogonType Interactive -RunLevel Highest',script)
        self.assertIn("$taskTrigger.Delay='PT15S'",script)
        self.assertIn("folder''s pet",script)
        self.assertNotIn('ROOT_VALUE',script)

    def test_migration_and_delete_are_scoped_to_exact_native_path(self):
        script=StartupManager(Path('test')).script('migrate')
        self.assertIn("-TaskPath '\\WuwaTappo\\'",script)
        self.assertIn(".Execute.Trim('\"') -ieq $taskNative",script)
        self.assertIn("-not $taskOwn -and $taskOldEnabled",script)
        self.assertLess(script.index('Register-ScheduledTask'),script.index('foreach($taskOld'))
        self.assertIn('foreach($taskOld in $taskLegacy)',script)

    def test_subprocess_is_hidden_encoded_and_result_is_verified(self):
        manager=StartupManager(Path('test'))
        with patch('startup_manager.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{"enabled":true,"launcher_verified":true}',stderr='')) as run:
            result=manager.run('status')
            self.assertTrue(result['enabled'])
            args,kwargs=run.call_args
            self.assertEqual(base64.b64decode(args[0][-1]).decode('utf-16le'),manager.script('status'))
            self.assertEqual(kwargs['creationflags'],0x08000000)
        with self.assertRaises(ValueError):manager.script('arbitrary-command')

    def test_failed_registration_is_reported_not_marked_enabled(self):
        with patch('startup_manager.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='denied',stdout='')):
            with self.assertRaisesRegex(RuntimeError,'denied'):StartupManager(Path('test')).run('enable')


if __name__=='__main__':unittest.main()
