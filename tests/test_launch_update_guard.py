"""Execute the real launcher guard without elevation or launching applications."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name=='nt','Windows launcher')
class LauncherUpdateTests(unittest.TestCase):
    def test_active_update_blocks_manual_start_but_allows_helper_and_stale_recovery(self):
        source=(Path(__file__).resolve().parents[1]/'installer/launch.ps1').read_text(encoding='utf-8-sig')
        guard=source[source.index(' # A manual re-open'):source.index(' # Do not pass a frozen')]
        for mode,expected in [('manual',False),('helper',True),('stale',True),('complete',True)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);job='a'*32
                prefix=f'''$ErrorActionPreference='Stop'
$UpdateJob='{job if mode=='helper' else ''}'
$taskJob='{job}'
$taskUpdates=Join-Path $PSScriptRoot '.updates'
$taskFolder=Join-Path $taskUpdates $taskJob
New-Item -ItemType Directory -Path $taskFolder -Force|Out-Null
@{{job=$taskJob;version='1.3.6'}}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $taskUpdates 'install-current.json') -Encoding UTF8
$taskOwner=Get-Process -Id $PID
$taskStarted=([DateTimeOffset]$taskOwner.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds()/1000
@{{phase='{'complete' if mode=='complete' else 'installing'}';pid=$PID;process_started=($taskStarted-{'10' if mode=='stale' else '0'})}}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $taskFolder 'progress.json') -Encoding UTF8
'''
                script=root/'guard.ps1';script.write_text(prefix+guard+"\nSet-Content -LiteralPath (Join-Path $PSScriptRoot 'continued') -Value yes\n",encoding='utf-8-sig')
                result=subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-File',str(script)],capture_output=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
                self.assertEqual((root/'continued').exists(),expected)

if __name__=='__main__':unittest.main()
