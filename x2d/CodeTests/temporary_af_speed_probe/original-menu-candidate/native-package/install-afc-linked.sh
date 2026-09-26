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
hashok /system/lib64/libx2d_native_menu.so b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
hashok /system/lib64/libx2d_native_menu.so.before-afc b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
hashok /blackbox/x2d-original-menu-stage/libx2d_native_menu.so c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
[ ! -L /system/lib64/libx2d_native_menu.so ] && [ ! -e /system/lib64/libx2d_native_menu.so.live-before-afc ] && [ ! -L /system/lib64/libx2d_native_menu.so.live-before-afc ] && [ ! -e /system/lib64/libx2d_native_menu.so.x2d-next ] && [ ! -L /system/lib64/libx2d_native_menu.so.x2d-next ]

hashok /system/etc/X2dNativeMenuBootstrap.qml 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
hashok /system/etc/X2dNativeMenuBootstrap.qml.before-afc 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
[ ! -L /system/etc/X2dNativeMenuBootstrap.qml ] && [ ! -e /system/etc/X2dNativeMenuBootstrap.qml.live-before-afc ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.live-before-afc ] && [ ! -e /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ]
hashok /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu 1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688
[ ! -e /system/etc/init/camera-gui.rc.before-x2d-native-menu ]
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
[ ! -e /system/etc/init/x2d-preview-loader.rc.before-x2d-native-menu ]
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-early-menu d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
[ ! -e /system/etc/init/x2d-preview-loader.rc.before-early-menu ]
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-native-input 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
[ ! -e /system/etc/init/x2d-preview-loader.rc.before-native-input ]
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
hashok /system/lib64/libx2d_native_menu.so.before-afc b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
saved="/system/lib64/libx2d_native_menu.so "$saved
cat /blackbox/x2d-original-menu-stage/libx2d_native_menu.so > /system/lib64/libx2d_native_menu.so.x2d-next
chmod 0644 /system/lib64/libx2d_native_menu.so.x2d-next
hashok /system/lib64/libx2d_native_menu.so.x2d-next c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
mv -f /system/lib64/libx2d_native_menu.so.x2d-next /system/lib64/libx2d_native_menu.so
hashok /system/lib64/libx2d_native_menu.so c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5

hashok /system/etc/X2dNativeMenuBootstrap.qml.before-afc 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
saved="/system/etc/X2dNativeMenuBootstrap.qml "$saved
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml > /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
chmod 0644 /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
hashok /system/etc/X2dNativeMenuBootstrap.qml.x2d-next 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
mv -f /system/etc/X2dNativeMenuBootstrap.qml.x2d-next /system/etc/X2dNativeMenuBootstrap.qml
hashok /system/etc/X2dNativeMenuBootstrap.qml 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
sync
restore_ro
[ "$(state)" = "$baseline" ]
success=1
start camera-gui
stopped=0
echo AFC_UPDATE_INSTALLED_READONLY
