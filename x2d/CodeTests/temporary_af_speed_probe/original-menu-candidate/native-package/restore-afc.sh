#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
[ ! -L /system/lib64/libx2d_native_menu.so ] && [ ! -L /system/lib64/libx2d_native_menu.so.before-afc ] && [ ! -e /system/lib64/libx2d_native_menu.so.x2d-next ] && [ ! -L /system/lib64/libx2d_native_menu.so.x2d-next ]
hashok /system/lib64/libx2d_native_menu.so c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
hashok /system/lib64/libx2d_native_menu.so.before-afc b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
[ ! -L /system/etc/X2dNativeMenuBootstrap.qml ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.before-afc ] && [ ! -e /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ]
hashok /system/etc/X2dNativeMenuBootstrap.qml 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
hashok /system/etc/X2dNativeMenuBootstrap.qml.before-afc 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
stopped=0
finish() { sync; restore_ro; if [ "$stopped" = 1 ]; then start camera-gui; fi; }
trap finish EXIT
trap 'exit 40' HUP INT TERM
[ "$(getprop init.svc.camera-gui)" = running ]
set -- $(pidof camera-gui)
[ "$#" = 1 ]
stopped=1
stop camera-gui
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 41; fi
mount -o remount,rw /system
cat /system/lib64/libx2d_native_menu.so.before-afc > /system/lib64/libx2d_native_menu.so.x2d-next
chmod 0644 /system/lib64/libx2d_native_menu.so.x2d-next
hashok /system/lib64/libx2d_native_menu.so.x2d-next b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
mv -f /system/lib64/libx2d_native_menu.so.x2d-next /system/lib64/libx2d_native_menu.so
cat /system/etc/X2dNativeMenuBootstrap.qml.before-afc > /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
chmod 0644 /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
hashok /system/etc/X2dNativeMenuBootstrap.qml.x2d-next 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
mv -f /system/etc/X2dNativeMenuBootstrap.qml.x2d-next /system/etc/X2dNativeMenuBootstrap.qml
sync
restore_ro
[ "$(state)" = "$baseline" ]
start camera-gui
stopped=0
echo ORIGINAL_MENU_AFC_UPDATE_RESTORED
