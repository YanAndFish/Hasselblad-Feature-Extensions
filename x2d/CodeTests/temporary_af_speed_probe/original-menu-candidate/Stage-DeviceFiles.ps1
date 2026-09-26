$ErrorActionPreference='Stop'
$parent=Split-Path $PSScriptRoot -Parent
Add-Type -TypeDefinition (Get-Content "$parent/AdbUsbCheck.cs" -Raw)
$stage='/blackbox/x2d-original-menu-stage'
$package=Join-Path $PSScriptRoot 'native-package'
$commands=[Collections.Generic.List[string]]::new()
$commands.Add('test -d '+$stage+' && test ! -L '+$stage+' && echo ORIGINAL_MENU_STAGE_OK')
$bytes=[IO.File]::ReadAllBytes("$package/files.tar.gz")
$encoded=[Convert]::ToBase64String($bytes)
for($i=0;$i -lt $encoded.Length;$i+=2800) {
 $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
 $commands.Add("printf %s '$part' $op $stage/files.b64 && echo ORIGINAL_MENU_STAGE_OK")
}
$hash=(Get-FileHash "$package/files.tar.gz").Hash.ToLowerInvariant()
$commands.Add('base64 -d '+$stage+'/files.b64 > '+$stage+'/files.tar.gz && set -- $(sha256sum '+$stage+'/files.tar.gz); [ "$1" = '+$hash+' ] && echo ORIGINAL_MENU_STAGE_OK')
$commands.Add('cd '+$stage+' && tar -xzf files.tar.gz && sh -n install-files.sh && echo ORIGINAL_MENU_STAGE_OK')
$null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'ORIGINAL_MENU_STAGE_OK')
$manifest=Get-Content "$package/package.json" -Raw | ConvertFrom-Json
$verify=[Collections.Generic.List[string]]::new()
foreach($f in $manifest.files) {
 $verify.Add('set -- $(sha256sum '+$stage+'/'+$f.source+'); [ "$1" = '+$f.sha256+' ] && echo ORIGINAL_MENU_STAGE_OK')
}
$null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($verify.ToArray(),'ORIGINAL_MENU_STAGE_OK')
'ORIGINAL_MENU_STAGED_VERIFIED'
