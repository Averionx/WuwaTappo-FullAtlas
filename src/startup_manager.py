"""Own the variant's logon task; never start the native pet without its host."""
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import threading


class StartupManager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.name = 'FullAtlas-' + hashlib.sha256(str(self.root).lower().encode()).hexdigest()[:12]
        self.lock = threading.Lock()

    def script(self, action):
        if action not in ('status', 'enable', 'disable', 'migrate'):
            raise ValueError('Unknown startup action')
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        return r'''
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$taskRoot=ROOT_VALUE
$taskName=NAME_VALUE
$taskAction=ACTION_VALUE
$taskPath='\WuwaTappoFullAtlas\'
$taskNative=Join-Path $taskRoot 'WuwaTappo.Local.exe'
$taskLauncher=Join-Path $taskRoot 'launch.ps1'
$taskPowerShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$taskArguments='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$taskLauncher+'"'
$taskOwn=Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
# The official app uses a shared task name. Touch it only when its action is
# exactly this installation's native executable, never another installation.
$taskLegacy=@(Get-ScheduledTask -TaskPath '\WuwaTappo\' -ErrorAction SilentlyContinue|Where-Object {
 @($_.Actions).Count -eq 1 -and $_.Actions[0].Execute.Trim('"') -ieq $taskNative
})
$taskOldEnabled=@($taskLegacy|Where-Object {$_.Settings.Enabled}).Count -gt 0
if($taskAction -eq 'enable' -or ($taskAction -eq 'migrate' -and -not $taskOwn -and $taskOldEnabled)){
 if(-not(Test-Path -LiteralPath $taskLauncher)){throw '启动器不存在，未更改开机自启动。'}
 $taskUser=[Security.Principal.WindowsIdentity]::GetCurrent().Name
 $taskTrigger=New-ScheduledTaskTrigger -AtLogOn -User $taskUser
 $taskTrigger.Delay='PT15S'
 $taskPrincipal=New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Highest
 $taskSettings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
 $taskLaunch=New-ScheduledTaskAction -Execute $taskPowerShell -Argument $taskArguments -WorkingDirectory $taskRoot
 $taskOwn=Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $taskLaunch -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'WuwaTappo全图鉴版：先启动本地服务，再启动桌宠。' -Force
}
if($taskAction -eq 'disable' -and $taskOwn){
 Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false
 $taskOwn=$null
}
if($taskAction -in @('enable','disable','migrate') -and ($taskOwn -or $taskAction -eq 'disable')){
 foreach($taskOld in $taskLegacy){Unregister-ScheduledTask -TaskPath $taskOld.TaskPath -TaskName $taskOld.TaskName -Confirm:$false}
}
$taskValid=$taskOwn -and $taskOwn.Settings.Enabled -and @($taskOwn.Actions).Count -eq 1 -and $taskOwn.Actions[0].Execute -ieq $taskPowerShell -and $taskOwn.Actions[0].Arguments -ceq $taskArguments
@{enabled=[bool]($taskValid -or ($taskAction -eq 'status' -and $taskOldEnabled));launcher_verified=[bool]$taskValid;migrated=[bool]($taskAction -eq 'migrate' -and $taskValid -and $taskOldEnabled)}|ConvertTo-Json -Compress
'''.replace('ROOT_VALUE', quote(self.root)).replace('NAME_VALUE', quote(self.name)).replace('ACTION_VALUE', quote(action))

    def run(self, action):
        with self.lock:
            encoded = base64.b64encode(self.script(action).encode('utf-16le')).decode('ascii')
            powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                    capture_output=True, encoding='utf-8-sig', errors='replace',
                                    creationflags=0x08000000, timeout=45)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or '开机自启动设置失败，请通过启动器以管理员权限运行。')
            return json.loads(result.stdout.strip())
