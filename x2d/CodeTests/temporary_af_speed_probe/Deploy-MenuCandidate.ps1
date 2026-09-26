param([ValidateSet('Build','Stage','Install','Remove')][string]$Action='Build')
$ErrorActionPreference='Stop'
$dir=Join-Path $PSScriptRoot 'menu-candidate'
$stage='/blackbox/x2d-menu-stage'
$meta=Get-Content -LiteralPath "$dir/package.json" -Raw | ConvertFrom-Json
$targets=@('/system/lib64/libx2d_menu_gate.so','/system/etc/x2d-menu-v1-main.qml','/system/etc/x2d-menu-candidate.sh')
if(($meta.files.target -join '|') -ne ($targets -join '|')){throw 'Unexpected candidate targets'}
foreach($e in $meta.files){
    if((Get-FileHash -LiteralPath (Join-Path $dir $e.source)).Hash.ToLowerInvariant() -ne $e.sha256){throw 'Candidate source differs'}
}
$header=@'
set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
# The normal maintenance domain verifies the original GUI before staging.
# This su-domain transaction only touches our system_file additions.
hashok /system/etc/x2d-preview-loader.sh abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085

'@
$install=$header
$remove=$header
foreach($e in $meta.files){
    $name=Split-Path $e.source -Leaf
    $install+='[ ! -e '+$e.target+' ] && [ ! -L '+$e.target+' ] || exit 34'+"`n"
    $install+='hashok '+$stage+'/'+$name+' '+$e.sha256+"`n"
    $remove+='if [ -e '+$e.target+' ]; then [ ! -L '+$e.target+' ] && hashok '+$e.target+' '+$e.sha256+' || exit 35; fi'+"`n"
}
$install+=@'
made=''
done_ok=0
finish() { if [ "$done_ok" = 0 ]; then for f in $made; do /system/bin/rm -f "$f"; done; fi; restore; }
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 10; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system

'@
foreach($e in $meta.files){
    $name=Split-Path $e.source -Leaf
    $install+='( set -C; : > '+$e.target+' )'+"`n"
    $install+='made="'+$e.target+' $made"'+"`n"
    $install+='/system/bin/cat '+$stage+'/'+$name+' > '+$e.target+"`n"
    $install+='/system/bin/chmod 0644 '+$e.target+"`n"
    $install+='hashok '+$e.target+' '+$e.sha256+"`n"
}
$install+="/system/bin/sync`ndone_ok=1`nrestore`n"+'[ "$(state)" = "$original" ] || exit 44'+"`necho MENU_CANDIDATE_INSTALLED_OLD_BOOT_UNCHANGED`n"
$remove+="trap restore EXIT`n"+"/system/bin/mount -o remount,rw /system`n"
foreach($target in $targets){$remove+='/system/bin/rm -f '+$target+"`n"}
$remove+="/system/bin/sync`nrestore`necho MENU_CANDIDATE_FILES_REMOVED`n"
[IO.File]::WriteAllText("$dir/install.sh",$install.Replace("`r`n","`n"),[Text.Encoding]::ASCII)
[IO.File]::WriteAllText("$dir/remove.sh",$remove.Replace("`r`n","`n"),[Text.Encoding]::ASCII)
if($Action -eq 'Build'){'MENU_DEPLOY_SCRIPTS_BUILT_NO_CAMERA_ACCESS';return}
if($Action -in @('Install','Remove')){
    $name=if($Action -eq 'Install'){'install.sh'}else{'remove.sh'}
    $hash=(Get-FileHash -LiteralPath "$dir/$name").Hash.ToLowerInvariant()
    $command='set -- $(/system/bin/sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && /system/bin/sh '+$stage+'/'+$name
    $src=Get-Content -LiteralPath "$PSScriptRoot/AdbUsbCheck.cs" -Raw
    $anchor='        private static string RunShell(string script) {'
    $method='public static string ApplyMenu(){return RunShell(@"'+$command.Replace('"','""')+'");}'
    if(-not $src.Contains($anchor)){throw 'Unexpected ADB helper'}
    Add-Type -TypeDefinition $src.Replace($anchor,$method+"`n"+$anchor)
    [X2DAdbCheck.AdbUsbCheck]::ApplyMenu();return
}
. "$PSScriptRoot/Usb.ps1"
$check=(Read-ReviewedUsb @('sha256sum /system/bin/camera-gui',"test ! -e $stage && test ! -L $stage && echo MENU_STAGE_ABSENT")) -join "`n"
if($check -notmatch '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0' -or $check -notmatch 'MENU_STAGE_ABSENT'){throw 'Unexpected camera/staging state'}
$null=Read-ReviewedUsb @("mkdir -m 700 $stage")
$sources=@($meta.files.source)+@('install.sh','remove.sh')
foreach($source in $sources){
    $path=Join-Path $dir $source;$name=Split-Path $source -Leaf
    $hash=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
    $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
    $commands=[Collections.Generic.List[string]]::new()
    for($i=0;$i -lt $encoded.Length;$i+=132){
        $chunk=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
        $commands.Add("printf %s '$chunk' $op $stage/$name.b64")
        if($commands.Count -eq 20){$null=Read-ReviewedUsb $commands.ToArray();$commands.Clear();Start-Sleep -Milliseconds 50}
    }
    if($commands.Count){$null=Read-ReviewedUsb $commands.ToArray()}
    $remote=(Read-ReviewedUsb @("base64 -d $stage/$name.b64 > $stage/$name && sha256sum $stage/$name")) -join "`n"
    if($remote -notmatch $hash){throw "Staging hash mismatch: $name"}
    Write-Output "STAGED $name"
}
