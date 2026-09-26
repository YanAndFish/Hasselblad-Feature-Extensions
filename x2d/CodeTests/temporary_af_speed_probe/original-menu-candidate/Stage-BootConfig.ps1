$ErrorActionPreference='Stop'
$parent=Split-Path $PSScriptRoot -Parent
Add-Type -TypeDefinition (Get-Content "$parent/AdbUsbCheck.cs" -Raw)
$stage='/blackbox/x2d-original-menu-stage'
$package=Join-Path $PSScriptRoot 'native-package'
$commands=[Collections.Generic.List[string]]::new()
$commands.Add('test -d '+$stage+' && test ! -L '+$stage+' && echo ORIGINAL_MENU_BOOT_STAGE_OK')
foreach($name in @('camera-gui.rc.native','x2d-preview-loader.rc.manual','activate-boot.sh','restore-boot.sh')) {
 $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes("$package/$name"))
 for($i=0;$i -lt $encoded.Length;$i+=2800) {
  $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
  $commands.Add("printf %s '$part' $op $stage/$name.b64 && echo ORIGINAL_MENU_BOOT_STAGE_OK")
 }
 $hash=(Get-FileHash "$package/$name").Hash.ToLowerInvariant()
 $commands.Add('base64 -d '+$stage+'/'+$name+'.b64 > '+$stage+'/'+$name+' && set -- $(sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && echo ORIGINAL_MENU_BOOT_STAGE_OK')
}
$commands.Add('sh -n '+$stage+'/activate-boot.sh && sh -n '+$stage+'/restore-boot.sh && echo ORIGINAL_MENU_BOOT_STAGE_OK')
$null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'ORIGINAL_MENU_BOOT_STAGE_OK')
'ORIGINAL_MENU_BOOT_STAGED_VERIFIED'
