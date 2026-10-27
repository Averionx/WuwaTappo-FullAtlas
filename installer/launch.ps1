param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
$taskPrincipal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
 $taskArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'))
 if($CheckOnly){$taskArgs+='-CheckOnly'}
 Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $taskArgs
 exit
}
try{
 & (Join-Path $PSScriptRoot 'initialize.ps1')
 $taskConfig=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'local_config.json') -Raw|ConvertFrom-Json
 $taskHostExe=Join-Path $PSScriptRoot 'LocalGalleryHost.exe'
 $taskListener=Get-NetTCPConnection -LocalPort $taskConfig.port -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
 if($taskListener){
  $taskOwner=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskListener.OwningProcess)
  if($taskOwner.ExecutablePath -ne $taskHostExe){throw '本地服务端口被其他程序占用，请先关闭占用程序。'}
 }else{
  Start-Process -FilePath $taskHostExe -WindowStyle Hidden -WorkingDirectory $PSScriptRoot -RedirectStandardOutput (Join-Path $PSScriptRoot 'host.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'host.stderr.log')
 }
 $taskStatus=$null
 for($taskTry=0;$taskTry -lt 60;$taskTry++){
  try{$taskStatus=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$taskConfig.port+'/status') -TimeoutSec 2;break}catch{Start-Sleep -Milliseconds 500}
 }
 if(-not $taskStatus.ready){throw '本地素材服务尚未就绪，请查看 host.stderr.log。'}
 if(-not $CheckOnly){Start-Process -FilePath (Join-Path $PSScriptRoot 'WuwaTappo.Local.exe') -WorkingDirectory $PSScriptRoot|Out-Null}
 @{ok=$true;ready=$taskStatus.ready;enabled=$taskStatus.enabled}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'launch_result.json') -Encoding UTF8
}catch{
 @{ok=$false;error=$_.Exception.Message}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'launch_result.json') -Encoding UTF8
 Add-Type -AssemblyName System.Windows.Forms
 [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'WuwaTappo全图鉴版')|Out-Null
 exit 1
}
