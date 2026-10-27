param([switch]$Cleanup)
$ErrorActionPreference='Stop'
$taskPrincipal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
 $taskArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'))
 if($Cleanup){$taskArgs+='-Cleanup'}
 Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $taskArgs
 exit
}
try{
 $taskConfig=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'local_config.json') -Raw|ConvertFrom-Json
 $taskListener=Get-NetTCPConnection -LocalPort $taskConfig.port -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
 if($taskListener){
  $taskOwner=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskListener.OwningProcess)
  if($taskOwner.ExecutablePath -ne (Join-Path $PSScriptRoot 'LocalGalleryHost.exe')){throw 'Unexpected port owner'}
  Invoke-RestMethod -Uri ('http://127.0.0.1:'+$taskConfig.port+'/mode') -Method Post -Headers @{'X-Local-Token'=$taskConfig.token} -ContentType 'application/json' -Body '{"enabled":false}' -TimeoutSec 60|Out-Null
 }else{
  $taskRestore=Start-Process -FilePath (Join-Path $PSScriptRoot 'LocalGalleryHost.exe') -WindowStyle Hidden -Wait -PassThru -ArgumentList '--restore-firewall'
  if($taskRestore.ExitCode -ne 0){throw '移除本地版防火墙规则失败'}
 }
 if($Cleanup){
  $taskExact=@((Join-Path $PSScriptRoot 'WuwaTappo.Local.exe'),(Join-Path $PSScriptRoot 'LocalGalleryHost.exe'))
  $taskRuntime=Join-Path $PSScriptRoot 'runtime\'
  Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath -and ($taskExact -contains $_.ExecutablePath -or $_.ExecutablePath.StartsWith($taskRuntime,[StringComparison]::OrdinalIgnoreCase))}|ForEach-Object{Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}
 }
}catch{
 Add-Type -AssemblyName System.Windows.Forms
 [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'恢复本地版联网失败')|Out-Null
 exit 1
}
