"""仅生成本地安装、恢复及受限 GUI 重载脚本；不会连接相机。"""
from pathlib import Path
import json
from prepare_device_animation import prepare

D=Path(__file__).resolve().parent
O=D/'outputs/device-package'
STAGE='/blackbox/x2d-shutter-stage'


def main():
    manifest=prepare()
    old=manifest['originalBootstrapSha256']
    targets={entry['source']:entry for entry in manifest['files']}
    boot='/system/etc/X2dNativeMenuBootstrap.qml'
    overlay='/system/etc/X2dShutterAnimation.qml'
    backup=boot+'.before-shutter'
    new=targets['X2dNativeMenuBootstrap.qml']['sha256']
    animation=targets['X2dShutterAnimation.qml']['sha256']
    header='''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
'''
    install=header+f'''hashok {boot} {old}
[ ! -L {boot} ] && [ ! -e {backup} ] && [ ! -L {backup} ]
[ ! -e {overlay} ] && [ ! -L {overlay} ]
[ ! -e {boot}.shutter-next ] && [ ! -L {boot}.shutter-next ]
[ ! -e {overlay}.shutter-next ] && [ ! -L {overlay}.shutter-next ]
hashok {STAGE}/X2dNativeMenuBootstrap.qml {new}
hashok {STAGE}/X2dShutterAnimation.qml {animation}
success=0; backup_ready=0; overlay_created=0
finish() {{
 if [ "$success" != 1 ]; then
  if [ "$backup_ready" = 1 ]; then cat {backup} > {boot}.shutter-next; chmod 0644 {boot}.shutter-next; mv -f {boot}.shutter-next {boot}; fi
  if [ "$overlay_created" = 1 ]; then rm -f {overlay}; fi
  rm -f {boot}.shutter-next {overlay}.shutter-next
  sync
 fi
 restore_ro
}}
trap finish EXIT
trap 'exit 40' HUP INT TERM
mount -o remount,rw /system
(set -C; : > {backup})
cat {boot} > {backup}
chmod 0644 {backup}
hashok {backup} {old}
backup_ready=1
cat {STAGE}/X2dShutterAnimation.qml > {overlay}.shutter-next
chmod 0644 {overlay}.shutter-next
hashok {overlay}.shutter-next {animation}
mv {overlay}.shutter-next {overlay}
overlay_created=1
cat {STAGE}/X2dNativeMenuBootstrap.qml > {boot}.shutter-next
chmod 0644 {boot}.shutter-next
hashok {boot}.shutter-next {new}
mv -f {boot}.shutter-next {boot}
sync
restore_ro
[ "$(state)" = "$baseline" ]
hashok {boot} {new}
hashok {overlay} {animation}
success=1
echo SHUTTER_FILES_INSTALLED_READONLY
'''
    restore=header+f'''hashok {backup} {old}
hashok {boot} {new}
hashok {overlay} {animation}
trap restore_ro EXIT
trap 'exit 40' HUP INT TERM
mount -o remount,rw /system
cat {backup} > {boot}.shutter-next
chmod 0644 {boot}.shutter-next
hashok {boot}.shutter-next {old}
mv -f {boot}.shutter-next {boot}
rm {overlay}
sync
restore_ro
[ "$(state)" = "$baseline" ]
echo SHUTTER_FILES_RESTORED_READONLY
'''
    reload='''#!/system/bin/sh
# 只在已授权安装后从既有 shell 域运行。一次受控重载，不创建重启循环。
set -eu
export PATH=/system/bin:/system/xbin:/sbin
test "$(getprop init.svc.camera-gui)" = running
pid=$(pidof camera-gui)
case "$pid" in ''|*[!0-9]*) exit 41;; esac
started=0
finish() { if [ "$started" = 0 ]; then start camera-gui; fi; }
trap finish EXIT
trap 'exit 42' HUP INT TERM
stop camera-gui
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 30 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 43; fi
# 新 QML 只允许本次人工重载重新挂接；构造器随即重建每次开机的保护标记。
test ! -L /tmp/x2d-native-menu-attempt
rm -f /tmp/x2d-native-menu-attempt
start camera-gui
started=1
echo SHUTTER_GUI_RELOAD_REQUESTED
'''
    for name,source in [('install.sh',install),('restore.sh',restore),('reload-gui.sh',reload)]:
        (O/name).write_text(source,encoding='utf-8',newline='\n')
    print('Prepared install, restoration, and one-shot GUI reload; no device access.')


if __name__=='__main__':
    main()
