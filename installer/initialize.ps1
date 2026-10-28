$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
$taskConfigPath=Join-Path $taskRoot 'local_config.json'
if(-not(Test-Path -LiteralPath $taskConfigPath)){
 $taskConfig=Get-Content -LiteralPath (Join-Path $taskRoot 'package_config.json') -Raw|ConvertFrom-Json
 $taskBytes=New-Object byte[] 32
 $taskRng=[Security.Cryptography.RandomNumberGenerator]::Create()
 try{$taskRng.GetBytes($taskBytes)}finally{$taskRng.Dispose()}
 $taskConfig|Add-Member -MemberType NoteProperty -Name token -Value ([Convert]::ToBase64String($taskBytes))
 $taskConfig|ConvertTo-Json|Set-Content -LiteralPath $taskConfigPath -Encoding UTF8
}
$taskConfig=Get-Content -LiteralPath $taskConfigPath -Raw|ConvertFrom-Json
$taskPackage=Get-Content -LiteralPath (Join-Path $taskRoot 'package_config.json') -Raw|ConvertFrom-Json
foreach($taskProperty in $taskPackage.PSObject.Properties){
 if($taskProperty.Name -ne 'token'){$taskConfig|Add-Member -MemberType NoteProperty -Name $taskProperty.Name -Value $taskProperty.Value -Force}
}
try{
 $taskManifest=Get-Content -LiteralPath (Join-Path $taskRoot 'cache\asset_manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
 $taskAtlas=Get-Content -LiteralPath (Join-Path $taskRoot 'cache\atlas.json') -Raw -Encoding UTF8|ConvertFrom-Json
 if(@($taskManifest.errors).Count -eq 0 -and @($taskManifest.records).Count -gt 0 -and @($taskAtlas.data).Count -gt 0){
  $taskConfig|Add-Member -MemberType NoteProperty -Name asset_count -Value @($taskManifest.records).Count -Force
  $taskConfig|Add-Member -MemberType NoteProperty -Name atlas_count -Value @($taskAtlas.data).Count -Force
 }
}catch{}
$taskConfig|ConvertTo-Json|Set-Content -LiteralPath $taskConfigPath -Encoding UTF8
if(-not(Test-Path -LiteralPath (Join-Path $taskRoot 'offline_state.json'))){[IO.File]::WriteAllText((Join-Path $taskRoot 'offline_state.json'),'{}')}
