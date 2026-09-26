# 仅恢复本次已核对的更新事务：旧映射已被原子替换，释放进程后恢复只读。
$ErrorActionPreference='Stop'
Add-Type -TypeDefinition (Get-Content "$(Split-Path $PSScriptRoot -Parent)/AdbUsbCheck.cs" -Raw)
$o=Join-Path $PSScriptRoot 'native-package'
$manifest=Get-Content "$PSScriptRoot/afc-update-manifest.json" -Raw | ConvertFrom-Json
$s=@'
#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ]
[ "$(pidof camera-gui)" = 365 ] && [ "$(getprop init.svc.camera-gui)" = running ]
# 构造器状态已从维护通道核对；su 域不能读取该 hbl 标签文件。
grep -q '^/dev/block/mmcblk0p17 /system ext4 rw,' /proc/mounts
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
'@
foreach($f in $manifest.changes) {
 $s+="`nhashok $($f.target) $($f.before)`nhashok $($f.target).before-afc $($f.before)`nhashok /blackbox/x2d-original-menu-stage/$($f.source) $($f.sha256)`n"
}
$s+=@'
stopped=0
finish() {
 sync
 mount -o remount,ro /system || true
 if [ "$stopped" = 1 ]; then start camera-gui; fi
}
trap finish EXIT
trap 'exit 40' HUP INT TERM
'@
foreach($f in $manifest.changes) {
 $t=$f.target
 $s+="`n[ ! -e $t.x2d-next ] && [ ! -L $t.x2d-next ]`ncat /blackbox/x2d-original-menu-stage/$($f.source) > $t.x2d-next`nchmod 0644 $t.x2d-next`nhashok $t.x2d-next $($f.sha256)`nmv -f $t.x2d-next $t`n"
}
$s+=@'
stop camera-gui
stopped=1
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 41; fi
sync
mount -o remount,ro /system
grep -q '^/dev/block/mmcblk0p17 /system ext4 ro,' /proc/mounts
# 用户授权的本轮新版本验证，只清除本扩展的单次尝试标记。
# 尝试标记由后续维护通道清除；su 不能移除该标签文件。
start camera-gui
stopped=0
echo AFC_UPDATE_RECOVERED_AND_GUI_STARTED
'@
$s=$s.Replace("`r`n","`n")+"`n"
[IO.File]::WriteAllText("$o/recover-afc.sh",$s,[Text.UTF8Encoding]::new($false))
$encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($s))
$commands=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt $encoded.Length;$i+=2800) {
 $part=$encoded.Substring($i,[Math]::Min(2800,$encoded.Length-$i));$op=if($i -eq 0){'>'}else{'>>'}
 $commands.Add("printf %s '$part' $op /blackbox/x2d-original-menu-stage/recover-afc.b64 && echo AFC_RECOVERY_STAGED")
}
$commands.Add('base64 -d /blackbox/x2d-original-menu-stage/recover-afc.b64 > /blackbox/x2d-original-menu-stage/recover-afc.sh && sh -n /blackbox/x2d-original-menu-stage/recover-afc.sh && echo AFC_RECOVERY_STAGED')
$null=[X2DAdbCheck.AdbUsbCheck]::RunShellBatch($commands.ToArray(),'AFC_RECOVERY_STAGED')
[X2DAdbCheck.AdbUsbCheck]::RunShellBatch(@('sh /blackbox/x2d-original-menu-stage/recover-afc.sh 2>&1'),'')
