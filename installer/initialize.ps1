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
if(-not(Test-Path -LiteralPath (Join-Path $taskRoot 'offline_state.json'))){[IO.File]::WriteAllText((Join-Path $taskRoot 'offline_state.json'),'{}')}
