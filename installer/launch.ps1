param([switch]$CheckOnly,[string]$UpdateJob='')
$ErrorActionPreference='Stop'
if(-not $UpdateJob){$UpdateJob=$env:WUWA_UPDATE_JOB}
Remove-Item -LiteralPath Env:WUWA_UPDATE_JOB -ErrorAction SilentlyContinue
$taskPrincipal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
 $taskArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'))
 if($CheckOnly){$taskArgs+='-CheckOnly'}
 Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $taskArgs
 exit
}
try{
 # A manual re-open during download/replacement must not lock the old EXE.
 # Only this update's helper may start the new version before health ACK.
 $taskUpdatePointer=Join-Path $PSScriptRoot '.updates\install-current.json'
 if(Test-Path -LiteralPath $taskUpdatePointer){
  try{
   $taskUpdate=Get-Content -LiteralPath $taskUpdatePointer -Raw|ConvertFrom-Json
   if($taskUpdate.job -match '^[0-9a-f]{32}$' -and $UpdateJob -ne $taskUpdate.job){
    $taskProgressPath=Join-Path $PSScriptRoot ('.updates\'+$taskUpdate.job+'\progress.json')
    $taskProgress=Get-Content -LiteralPath $taskProgressPath -Raw|ConvertFrom-Json
    if($taskProgress.phase -notin @('complete','failed')){
     $taskUpdateProcess=Get-Process -Id $taskProgress.pid -ErrorAction SilentlyContinue
     if($taskUpdateProcess){
      $taskProcessEpoch=([DateTimeOffset]$taskUpdateProcess.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds()/1000
      if([Math]::Abs($taskProcessEpoch-$taskProgress.process_started) -lt 1){exit}
     }
    }
   }
  }catch{Write-Verbose 'No active update owner found.'}
 }
 # Do not pass a frozen upgrader's temporary DLL directory into native children.
 if(-not ('WuwaTappoNativeLaunch' -as [type])){
  Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public static class WuwaTappoNativeLaunch { [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern bool SetDllDirectoryW(string value); }'
 }
 if(-not [WuwaTappoNativeLaunch]::SetDllDirectoryW($null)){throw '无法初始化本机运行库搜索路径。'}
 foreach($taskRuntimeName in @('VCRUNTIME140.dll','VCRUNTIME140_1.dll')){
  $taskRuntimeSource=Join-Path $PSScriptRoot ('_internal\'+$taskRuntimeName)
  $taskRuntimeTarget=Join-Path $PSScriptRoot $taskRuntimeName
  if(-not (Test-Path -LiteralPath $taskRuntimeSource)){throw ('缺少本机运行库：'+$taskRuntimeName)}
  if(-not (Test-Path -LiteralPath $taskRuntimeTarget)){
   Copy-Item -LiteralPath $taskRuntimeSource -Destination $taskRuntimeTarget
  }elseif((Get-FileHash -LiteralPath $taskRuntimeSource).Hash -ne (Get-FileHash -LiteralPath $taskRuntimeTarget).Hash){
   Copy-Item -LiteralPath $taskRuntimeSource -Destination $taskRuntimeTarget -Force
  }
 }
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
