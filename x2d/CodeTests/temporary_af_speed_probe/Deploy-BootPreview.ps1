param([ValidateSet('Compile','Stage','ResumeStage','Install','Remove')][string]$Action='Compile')
$ErrorActionPreference='Stop'
$dir=$PSScriptRoot
$meta=Get-Content -Raw "$dir/boot-preview-package.json" | ConvertFrom-Json
$stage='/blackbox/x2d-preview-stage'
$src=Get-Content -Raw "$dir/AdbUsbCheck.cs"
$methods=''
foreach($p in @(@('InstallPreview','install_preview_package.sh',$meta.installHash),@('RemovePreview','remove_preview_package.sh',$meta.removeHash))){
    $hash=(Get-FileHash -LiteralPath "$dir/$($p[1])" -Algorithm SHA256).Hash.ToLowerInvariant()
    if($hash -ne $p[2]){throw 'Package installer changed; rebuild and review'}
    $cmd='set -- $(/system/bin/sha256sum '+$stage+'/'+$p[1]+'); [ "$1" = '+$p[2]+' ] && /system/bin/sh '+$stage+'/'+$p[1]
    $methods+='public static string '+$p[0]+'(){ return RunShell(@"'+$cmd.Replace('"','""')+'"); }'+"`n"
}
$anchor='        private static string RunShell(string script) {'
if(-not $src.Contains($anchor)){throw 'ADB helper changed'}
if(-not ('X2DAdbCheck.AdbUsbCheck' -as [type])){Add-Type -TypeDefinition $src.Replace($anchor,$methods+$anchor)}
if($Action -eq 'Compile'){'DEPLOY_TOOL_COMPILED_NO_CAMERA_ACCESS';return}
if($Action -eq 'Install'){[X2DAdbCheck.AdbUsbCheck]::InstallPreview();return}
if($Action -eq 'Remove'){[X2DAdbCheck.AdbUsbCheck]::RemovePreview();return}
. "$dir/Usb.ps1"
$stageCheck=if($Action -eq 'Stage'){"test ! -e $stage && test ! -L $stage && echo STAGE_CHECKED"}else{"test -d $stage && test ! -L $stage && test ! -e /system/etc/init/x2d-preview-loader.rc && echo STAGE_CHECKED"}
$baseline=(Read-ReviewedUsb @('sha256sum /system/bin/camera-gui /system/bin/camera-test',$stageCheck)) -join "`n"
if($baseline -notmatch '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0' -or $baseline -notmatch 'e2621b84391d0e5601d9a22f9da460e982f7028bf5380e9f9d401a91380bb7b0' -or $baseline -notmatch 'STAGE_CHECKED'){throw 'Firmware/stage differs'}
if($Action -eq 'Stage'){$null=Read-ReviewedUsb @("mkdir -m 700 $stage")}
$names=@($meta.files | ForEach-Object {$_.source})+@('install_preview_package.sh','remove_preview_package.sh')
foreach($name in $names){
    $expected=(Get-FileHash -LiteralPath "$dir/$name" -Algorithm SHA256).Hash.ToLowerInvariant()
    if($Action -eq 'ResumeStage'){
        $current=(Read-ReviewedUsb @("sha256sum $stage/$name 2>/dev/null; true")).Trim().Split(' ')[0]
        if($current -eq $expected){continue}
    }
    $bytes=[IO.File]::ReadAllBytes("$dir/$name");$encoded=[Convert]::ToBase64String($bytes)
    $commands=[Collections.Generic.List[string]]::new()
    for($i=0;$i -lt $encoded.Length;$i+=132){
        $chunk=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$chunk' $op $stage/$name.b64")
        if($commands.Count -eq 20){$null=Read-ReviewedUsb $commands.ToArray();$commands.Clear();Start-Sleep -Milliseconds 50}
    }
    if($commands.Count){$null=Read-ReviewedUsb $commands.ToArray()}
    $remote=(Read-ReviewedUsb @("base64 -d $stage/$name.b64 > $stage/$name && sha256sum $stage/$name")).Trim().Split(' ')[0]
    $expected=(Get-FileHash -LiteralPath "$dir/$name" -Algorithm SHA256).Hash.ToLowerInvariant()
    if($remote -ne $expected){throw "Uploaded file differs: $name"}
}
'PREVIEW_PACKAGE_STAGED_NOT_INSTALLED'
