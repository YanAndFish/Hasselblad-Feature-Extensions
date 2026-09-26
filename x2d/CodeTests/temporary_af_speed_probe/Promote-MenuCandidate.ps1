param([ValidateSet('Build','Stage','Install','Rollback')][string]$Action='Build')
$ErrorActionPreference='Stop'
$dir=Join-Path $PSScriptRoot 'menu-candidate'
$stage='/blackbox/x2d-menu-stage'
$newHash=(Get-FileHash "$dir/boot_menu_candidate.sh").Hash.ToLowerInvariant()
$oldHash='abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085'
$candidateHash='ee88ba07aeb7711a2af505a7bba6381468a9dbb8a9e96bf52e594257761b9f12'
$header=@'
set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
boot=/system/etc/x2d-preview-loader.sh
candidate=/system/etc/x2d-menu-candidate.sh
backup=/system/etc/x2d-preview-loader.previous.sh
[ ! -L "$boot" ] && [ ! -L "$candidate" ] && [ ! -L "$backup" ] || exit 34

'@
$install=$header+@"
hashok `"`$boot`" $oldHash
hashok `"`$candidate`" $candidateHash
hashok $stage/boot_menu_fixed.sh $newHash
hashok /system/lib64/libx2d_menu_gate.so b1d2f86e8a650187d370ff964bd6afcda2227b7ca3aff87dbc890d5a7aaf844b
hashok /system/etc/x2d-menu-v1-main.qml 39ef3ee7b2e65db1776c769c03dc36333ced31c3e822ace90128a9ea901c7a0d
[ ! -e `"`$backup`" ] || exit 35

"@
$install+=@'
done_ok=0; backup_ready=0
finish() {
  if [ "$done_ok" = 0 ] && [ "$backup_ready" = 1 ]; then
    /system/bin/cat "$backup" > "$boot"
    /system/bin/chmod 0644 "$boot"
    /system/bin/sync
  fi
  restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 15; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
(set -C; : > "$backup")
/system/bin/cat "$boot" > "$backup"
/system/bin/chmod 0644 "$backup"

'@
$install+="hashok `"`$backup`" $oldHash`nbackup_ready=1`n"
$install+="/system/bin/cat $stage/boot_menu_fixed.sh > `"`$candidate`"`nhashok `"`$candidate`" $newHash`n"
$install+="/system/bin/cat $stage/boot_menu_fixed.sh > `"`$boot`"`n/system/bin/chmod 0644 `"`$boot`" `"`$candidate`"`nhashok `"`$boot`" $newHash`n"
$install+="/system/bin/sync`nrestore_mount`n"+'[ "$(state)" = "$original" ] || exit 44'+"`ndone_ok=1`necho HIDDEN_MENU_BOOT_INSTALLED`n"
$rollback=$header+"hashok `"`$boot`" $newHash`nhashok `"`$backup`" $oldHash`n"
$rollback+=@'
trap restore_mount EXIT
( /system/bin/sleep 15; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
/system/bin/cat "$backup" > "$boot"
/system/bin/chmod 0644 "$boot"

'@
$rollback+="hashok `"`$boot`" $oldHash`n/system/bin/sync`nrestore_mount`necho ORIGINAL_PREVIEW_BOOT_RESTORED`n"
[IO.File]::WriteAllText("$dir/promote.sh",$install.Replace("`r`n","`n"),[Text.Encoding]::ASCII)
[IO.File]::WriteAllText("$dir/rollback-boot.sh",$rollback.Replace("`r`n","`n"),[Text.Encoding]::ASCII)
if($Action -eq 'Build'){'PROMOTION_PREPARED_NO_DEVICE_ACCESS';return}
if($Action -in @('Install','Rollback')){
 $name=if($Action -eq 'Install'){'promote.sh'}else{'rollback-boot.sh'}
 $hash=(Get-FileHash "$dir/$name").Hash.ToLowerInvariant()
 $command='set -- $(/system/bin/sha256sum '+$stage+'/'+$name+'); [ "$1" = '+$hash+' ] && /system/bin/sh '+$stage+'/'+$name
 $src=Get-Content "$PSScriptRoot/AdbUsbCheck.cs" -Raw
 $anchor='        private static string RunShell(string script) {'
 if(-not $src.Contains($anchor)){throw 'Unexpected ADB helper'}
 $method='public static string PromoteMenu(){return RunShell(@"'+$command.Replace('"','""')+'");}'
 Add-Type -TypeDefinition $src.Replace($anchor,$method+"`n"+$anchor)
 [X2DAdbCheck.AdbUsbCheck]::PromoteMenu();return
}
. "$PSScriptRoot/Usb.ps1"
foreach($pair in @(@('boot_menu_candidate.sh','boot_menu_fixed.sh'),@('promote.sh','promote.sh'),@('rollback-boot.sh','rollback-boot.sh'))){
 $path="$dir/$($pair[0])";$name=$pair[1];$hash=(Get-FileHash $path).Hash.ToLowerInvariant()
 $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
 $cmds=[Collections.Generic.List[string]]::new()
 for($i=0;$i -lt $encoded.Length;$i+=132){
  $part=$encoded.Substring($i,[Math]::Min(132,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
  $cmds.Add("printf %s '$part' $op $stage/$name.b64")
  if($cmds.Count -eq 20){$null=Read-ReviewedUsb $cmds.ToArray();$cmds.Clear()}
 }
 if($cmds.Count){$null=Read-ReviewedUsb $cmds.ToArray()}
 $out=(Read-ReviewedUsb @("base64 -d $stage/$name.b64 > $stage/$name && sh -n $stage/$name && sha256sum $stage/$name")) -join "`n"
 if($out -notmatch $hash){throw "Staging hash mismatch: $name"}
 "STAGED $name"
}
