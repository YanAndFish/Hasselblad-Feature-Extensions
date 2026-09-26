#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ]
[ "$(pidof camera-gui)" = 365 ] && [ "$(getprop init.svc.camera-gui)" = running ]
[ "$(cat /tmp/x2d-native-menu-preload.status)" = BOOTSTRAP_POINTER_READY ]
grep -q '^/dev/block/mmcblk0p17 /system ext4 rw,' /proc/mounts
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
hashok /system/lib64/libx2d_native_menu.so b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
hashok /system/lib64/libx2d_native_menu.so.before-afc b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
hashok /blackbox/x2d-original-menu-stage/libx2d_native_menu.so c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5

hashok /system/etc/X2dNativeMenuBootstrap.qml 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
hashok /system/etc/X2dNativeMenuBootstrap.qml.before-afc 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
stopped=0
finish() {
 sync
 mount -o remount,ro /system || true
 if [ "$stopped" = 1 ]; then start camera-gui; fi
}
trap finish EXIT
trap 'exit 40' HUP INT TERM
[ ! -e /system/lib64/libx2d_native_menu.so.x2d-next ] && [ ! -L /system/lib64/libx2d_native_menu.so.x2d-next ]
cat /blackbox/x2d-original-menu-stage/libx2d_native_menu.so > /system/lib64/libx2d_native_menu.so.x2d-next
chmod 0644 /system/lib64/libx2d_native_menu.so.x2d-next
hashok /system/lib64/libx2d_native_menu.so.x2d-next c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
mv -f /system/lib64/libx2d_native_menu.so.x2d-next /system/lib64/libx2d_native_menu.so

[ ! -e /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ]
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml > /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
chmod 0644 /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
hashok /system/etc/X2dNativeMenuBootstrap.qml.x2d-next 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
mv -f /system/etc/X2dNativeMenuBootstrap.qml.x2d-next /system/etc/X2dNativeMenuBootstrap.qml
stop camera-gui
stopped=1
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 41; fi
sync
mount -o remount,ro /system
grep -q '^/dev/block/mmcblk0p17 /system ext4 ro,' /proc/mounts
# 用户授权的本轮新版本验证，只清除本扩展的单次尝试标记。
rm -f /tmp/x2d-native-menu-attempt
start camera-gui
stopped=0
echo AFC_UPDATE_RECOVERED_AND_GUI_STARTED
