$ErrorActionPreference='Stop'
Add-Type -TypeDefinition (Get-Content "$(Split-Path $PSScriptRoot -Parent)/AdbUsbCheck.cs" -Raw)
$o=Join-Path $PSScriptRoot 'native-package'
$manifest=Get-Content "$PSScriptRoot/afc-update-manifest.json" -Raw | ConvertFrom-Json
$s=@'
#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ]
[ "$(pidof camera-gui)" = 363 ] && [ "$(getprop init.svc.camera-gui)" = running ]
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
'@
foreach($f in $manifest.changes) {
 $t=$f.target
 $s+="`nhashok $t $($f.before)`nhashok $t.before-afc $($f.before)`nhashok /blackbox/x2d-original-menu-stage/$($f.source) $($f.sha256)`n"
 $s+="[ ! -L $t ] && [ ! -e $t.live-before-afc ] && [ ! -L $t.live-before-afc ] && [ ! -e $t.x2d-next ] && [ ! -L $t.x2d-next ]`n"
}
foreach($migration in $manifest.backupMigrations) {
 $s+="hashok /system/etc/X2dBackup-$($migration[0]) $($migration[1])`n[ ! -e /system/etc/init/$($migration[0]) ]`n"
}
$s+=@'
success=0; saved=''; stopped=0
finish() {
 if [ "$success" != 1 ]; then
   for path in $saved; do
     cat "$path.before-afc" > "$path.x2d-next"
     chmod 0644 "$path.x2d-next"
     mv -f "$path.x2d-next" "$path"
   done
   sync
 fi
 restore_ro
 if [ "$stopped" = 1 ]; then start camera-gui; fi
}
trap finish EXIT
trap 'exit 40' HUP INT TERM
# 设备不允许创建硬链接；先停止精确核对的 GUI，释放映射后再替换文件。
stopped=1
stop camera-gui
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 41; fi
mount -o remount,rw /system
'@
foreach($f in $manifest.changes) {
 $t=$f.target
 $s+="`nhashok $t.before-afc $($f.before)`n"
 $s+="saved=`"$t `"`$saved`ncat /blackbox/x2d-original-menu-stage/$($f.source) > $t.x2d-next`nchmod 0644 $t.x2d-next`nhashok $t.x2d-next $($f.sha256)`nmv -f $t.x2d-next $t`nhashok $t $($f.sha256)`n"
}
$s+=@'
sync
restore_ro
[ "$(state)" = "$baseline" ]
success=1
start camera-gui
stopped=0
echo AFC_UPDATE_INSTALLED_READONLY
'@
$s=$s.Replace("`r`n","`n")+"`n"
[IO.File]::WriteAllText("$o/install-afc-linked.sh",$s,[Text.UTF8Encoding]::new($false))
$encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($s))
$commands=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt $encoded.Length;$i+=2800) {
 $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
 $commands.Add("printf %s '$part' $op /blackbox/x2d-original-menu-stage/install-afc-linked.b64 && echo AFC_LINKED_STAGED")
}
$hash=(Get-FileHash "$o/install-afc-linked.sh").Hash.ToLowerInvariant()
$commands.Add('base64 -d /blackbox/x2d-original-menu-stage/install-afc-linked.b64 > /blackbox/x2d-original-menu-stage/install-afc-linked.sh && sh -n /blackbox/x2d-original-menu-stage/install-afc-linked.sh && set -- $(sha256sum /blackbox/x2d-original-menu-stage/install-afc-linked.sh); [ "$1" = '+$hash+' ] && echo AFC_LINKED_STAGED')
$null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'AFC_LINKED_STAGED')
[X2DAdbCheck.AdbUsbCheck]::RunShellBatch(@('sh /blackbox/x2d-original-menu-stage/install-afc-linked.sh 2>&1'),'')
