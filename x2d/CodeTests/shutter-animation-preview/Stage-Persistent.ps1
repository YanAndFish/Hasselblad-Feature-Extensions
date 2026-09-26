param([switch]$StageDevice)
$ErrorActionPreference='Stop'
if(-not $StageDevice){'Offline default. Prepare and review the package first. -StageDevice requires an already authorized temporary ADB session.';return}
$package=Join-Path $PSScriptRoot 'outputs/device-package'
$manifest=Get-Content (Join-Path $package 'persistent-package.json') -Raw | ConvertFrom-Json
$files=@($manifest.files | ForEach-Object {$_.source})+@('install-persistent.sh','restore-persistent.sh')
foreach($entry in $manifest.files){if((Get-FileHash (Join-Path $package $entry.source)).Hash.ToLowerInvariant() -ne $entry.sha256){throw 'Package differs'}}
. (Join-Path $PSScriptRoot '../temporary_af_speed_probe/Usb.ps1')
$state=@(Read-ReviewedUsb @('sha256sum /system/bin/camera-gui /system/etc/X2dShutterAnimation.qml','grep " /system " /proc/mounts'))
if($state[0] -notmatch '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0' -or $state[0] -notmatch 'cded1a09b5de14f73a8b9efcfa8f041dc40afd7c777f666f628cfe32e22245ae' -or $state[1] -notmatch ' ext4 ro,'){throw 'Camera baseline differs'}
if(-not ('X2DAdbCheck.AdbUsbCheck' -as [type])){Add-Type -TypeDefinition (Get-Content (Join-Path $PSScriptRoot '../temporary_af_speed_probe/AdbUsbCheck.cs') -Raw)}
$stage='/blackbox/x2d-shutter-stage'
foreach($name in $files){
    $path=Join-Path $package $name
    $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
    $commands=[Collections.Generic.List[string]]::new()
    for($i=0;$i -lt $encoded.Length;$i+=2800){
        $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$part' $op $stage/$name.b64 && echo PERSISTENT_STAGE_OK")
    }
    $hash=(Get-FileHash $path).Hash.ToLowerInvariant()
    $commands.Add('base64 -d '+$stage+'/'+$name+'.b64 > '+$stage+'/'+$name+' && set -- $(sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && echo PERSISTENT_STAGE_OK')
    if($name.EndsWith('.sh')){$commands.Add("sh -n $stage/$name && echo PERSISTENT_STAGE_OK")}
    $null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'PERSISTENT_STAGE_OK')
    "STAGED_VERIFIED $name"
}
'STAGED_ONLY_NOT_INSTALLED'
