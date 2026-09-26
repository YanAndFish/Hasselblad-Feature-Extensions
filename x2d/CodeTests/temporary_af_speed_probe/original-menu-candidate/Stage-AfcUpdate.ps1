$ErrorActionPreference='Stop'
$parent=Split-Path $PSScriptRoot -Parent
Add-Type -TypeDefinition (Get-Content "$parent/AdbUsbCheck.cs" -Raw)
$stage='/blackbox/x2d-original-menu-stage'
$package=Join-Path $PSScriptRoot 'native-package'
$commands=[Collections.Generic.List[string]]::new()
$commands.Add('test -d '+$stage+' && test ! -L '+$stage+' && echo AFC_UPDATE_STAGE_OK')
$encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes("$package/afc-update.tar.gz"))
for($i=0;$i -lt $encoded.Length;$i+=2800) {
 $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
 $commands.Add("printf %s '$part' $op $stage/afc-update.b64 && echo AFC_UPDATE_STAGE_OK")
}
$hash=(Get-FileHash "$package/afc-update.tar.gz").Hash.ToLowerInvariant()
$commands.Add('base64 -d '+$stage+'/afc-update.b64 > '+$stage+'/afc-update.tar.gz && set -- $(sha256sum '+$stage+'/afc-update.tar.gz); [ "$1" = '+$hash+' ] && echo AFC_UPDATE_STAGE_OK')
$commands.Add('cd '+$stage+' && tar -xzf afc-update.tar.gz && sh -n update-afc.sh && sh -n restore-afc.sh && sh -n restore-boot.sh && echo AFC_UPDATE_STAGE_OK')
$null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'AFC_UPDATE_STAGE_OK')
'AFC_UPDATE_STAGED_VERIFIED'
