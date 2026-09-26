#!/system/bin/sh
# 本轮独立临时试运行；原厂启动文件尚未改变。
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(sha256sum /system/bin/camera-gui | cut -d ' ' -f1)" = 16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0 ] || exit 31
[ "$(getprop init.svc.camera-gui)" = running ] || exit 32
[ "$(cat /tmp/x2d-preview/status)" = READY_NATIVE ] || exit 33
[ ! -e /tmp/x2d-preview-before-native-stock ] && [ ! -e /tmp/x2d-native-menu-attempt ] || exit 34
echo PAUSING_OWN_PREVIEW > /tmp/x2d-native-menu-test.status
touch /tmp/x2d-preview/stop
i=0
while [ "$(getprop init.svc.x2d-preview-loader)" != stopped ] && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
[ "$(getprop init.svc.x2d-preview-loader)" = stopped ] || exit 35
grep -q ORIGINAL_KEY_RESTORED /tmp/x2d-preview/loader.log || exit 36
set -- $(pidof camera-gui)
[ "$#" = 1 ] && [ "$1" = 2022 ] || exit 37
[ "$(awk '{print $22}' /proc/2022/stat)" = 30482 ] || exit 38
mv /tmp/x2d-preview /tmp/x2d-preview-before-native-stock
restore_stock() {
    start camera-gui
    start x2d-preview-loader
    echo RESTORED_STOCK > /tmp/x2d-native-menu-test.status
}
stop camera-gui
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then restore_stock; exit 39; fi
export XDG_RUNTIME_DIR=/tmp
export XDG_CACHE_HOME=/data
export QT_QPA_FONTDIR=/system/lib64/qt/lib/fonts
X2D_NATIVE_MENU=1 LD_PRELOAD=/system/lib64/libx2d_native_menu.so nohup /system/bin/camera-gui -platform wayland-egl --fullscreen > /tmp/x2d-native-menu-gui.log 2>&1 < /dev/null &
candidate=$!
echo "$candidate" > /tmp/x2d-native-menu-test.pid
sleep 1
if [ ! -r /proc/$candidate/stat ]; then restore_stock; exit 40; fi
stamp=$(awk '{print $22}' /proc/$candidate/stat)
echo "$stamp" > /tmp/x2d-native-menu-test.start
echo CANDIDATE_RUNNING > /tmp/x2d-native-menu-test.status
# 若候选退出，只恢复原厂服务；无定时弹窗、无成功后自动收起。
while [ ! -e /tmp/x2d-native-menu-test.stop ]; do
    if [ ! -r /proc/$candidate/stat ] || [ "$(awk '{print $22}' /proc/$candidate/stat)" != "$stamp" ]; then
        restore_stock; exit 41
    fi
    sleep 1
done
