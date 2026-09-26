param([switch]$StageDevice)
$ErrorActionPreference='Stop'
if(-not $StageDevice){'Offline default: prepare_install.py first; -StageDevice explicitly writes only the candidate staging directory.';return}
$package=Join-Path $PSScriptRoot 'outputs/device-package'
$stage='/blackbox/x2d-shutter-stage'
$manifest=Get-Content (Join-Path $package 'package.json') -Raw | ConvertFrom-Json
$files=@('X2dNativeMenuBootstrap.qml','X2dShutterAnimation.qml','install.sh','restore.sh','reload-gui.sh')
foreach($entry in $manifest.files){if((Get-FileHash (Join-Path $package $entry.source)).Hash.ToLowerInvariant() -ne $entry.sha256){throw 'Package differs.'}}
. (Join-Path $PSScriptRoot '../temporary_af_speed_probe/Usb.ps1')
$checks=Read-ReviewedUsb @('sha256sum /system/bin/camera-gui /system/etc/X2dNativeMenuBootstrap.qml','grep " /system " /proc/mounts')
if($checks[0] -notmatch $manifest.guiSha256 -or $checks[0] -notmatch $manifest.originalBootstrapSha256 -or $checks[1] -notmatch ' ext4 ro,'){throw 'Camera baseline differs.'}
$null=Read-ReviewedUsb @("test ! -e $stage && test ! -L $stage && mkdir -m 700 $stage && echo SHUTTER_STAGE_CREATED")
foreach($name in $files){
    $local=Join-Path $package $name
    $hash=(Get-FileHash -LiteralPath $local).Hash.ToLowerInvariant()
    $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($local))
    $commands=[Collections.Generic.List[string]]::new()
    for($i=0;$i -lt $encoded.Length;$i+=132){
        $part=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i))
        $op=if($i -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$part' $op $stage/$name.b64")
        if($commands.Count -eq 40){$null=Read-ReviewedUsb $commands.ToArray();$commands.Clear()}
    }
    if($commands.Count){$null=Read-ReviewedUsb $commands.ToArray()}
    $result=(Read-ReviewedUsb @("base64 -d $stage/$name.b64 > $stage/$name && sha256sum $stage/$name")) -join "`n"
    if(-not $result.StartsWith($hash)){throw "Remote hash differs: $name"}
    if($name.EndsWith('.sh')){$null=Read-ReviewedUsb @("sh -n $stage/$name")}
    "STAGED_VERIFIED $name"
}
'STAGED_ONLY_NOT_INSTALLED'
