#!/system/bin/sh
# 一次性原厂调试界面验证；不安装 AF-C，不修改系统文件。
set -u
export PATH=/system/bin:/system/xbin:/sbin
d=/tmp/x2d-debug-entry-check
baseline=rndis,mass_storage,bulk,acm
debug=rndis,mass_storage,bulk,acm,adb
restoring=0
restore() {
    [ "$restoring" = 0 ] || return
    restoring=1
    trap - EXIT HUP INT TERM
    if ! mkdir "$d/restore-lock" 2>/dev/null; then return; fi
    echo RESTORING > "$d/status"
    cfg=$(getprop sys.usb.config)
    if [ "$cfg" = "$debug" ]; then
        setprop sys.usb.config none
        sleep 1
        setprop sys.usb.config "$baseline"
    elif [ "$cfg" != "$baseline" ]; then
        echo RESTORE_USB_CONFLICT > "$d/status"; return
    fi
    i=0
    while [ "$(getprop sys.usb.state)" != "$baseline" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i+1)); done
    [ "$(getprop sys.usb.state)" = "$baseline" ] || { echo RESTORE_USB_FAILED > "$d/status"; return; }
    if [ -e "$d/gui-restarted" ]; then
        /system/bin/odindb-send --print-cmdline -s gui -p osd_clock -- E_OSDClock_Off >> "$d/restore.log" 2>&1
        stop camera-gui
        i=0
        while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i+1)); done
        if pidof camera-gui >/dev/null 2>&1; then echo RESTORE_GUI_STOP_FAILED > "$d/status"; return; fi
        start camera-gui
        sleep 3
    fi
    [ "$(getprop init.svc.camera-gui)" = running ] || { echo RESTORE_GUI_FAILED > "$d/status"; return; }
    if [ -d "$d/preview-before" ] && [ ! -e /tmp/x2d-preview ]; then
        start x2d-preview-loader
        i=0
        while [ "$(cat /tmp/x2d-preview/status 2>/dev/null)" != READY_NATIVE ] && [ "$i" -lt 400 ]; do sleep 0.1; i=$((i+1)); done
        [ "$(cat /tmp/x2d-preview/status 2>/dev/null)" = READY_NATIVE ] || { echo RESTORE_PREVIEW_FAILED > "$d/status"; return; }
    fi
    /system/bin/odindb-send --print-cmdline -s gui -p osd_clock >> "$d/restore.log" 2>&1
    getprop init.svc.camera-gui >> "$d/restore.log"
    getprop init.svc.camera-service >> "$d/restore.log"
    getprop sys.usb.config >> "$d/restore.log"
    echo RESTORED > "$d/status"
}
if [ "${1:-}" = restore ]; then restore; exit; fi
exec > "$d/run.log" 2>&1
[ "$(getprop sys.usb.config)" = "$baseline" ] || exit 20
[ "$(getprop init.svc.adbd)" = stopped ] || exit 21
[ "$(cat /tmp/x2d-preview/status)" = READY_NATIVE ] || exit 22
[ "$(sha256sum /system/bin/camera-gui | cut -d ' ' -f1)" = 16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0 ] || exit 23
[ ! -e "$d/preview-before" ] && [ ! -e "$d/restore-lock" ] || exit 24
trap restore EXIT
trap 'exit 25' HUP INT TERM
echo PAUSING_OWN_MENU > "$d/status"
touch /tmp/x2d-preview/stop
i=0
while [ "$(getprop init.svc.x2d-preview-loader)" != stopped ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i+1)); done
[ "$(getprop init.svc.x2d-preview-loader)" = stopped ] || exit 26
grep -q ORIGINAL_KEY_RESTORED /tmp/x2d-preview/loader.log || exit 27
set -- $(pidof camera-gui)
[ "$#" = 1 ] && [ "$1" = 365 ] || exit 28
[ "$(awk '{print $22}' /proc/365/stat)" = 60 ] || exit 29
mv /tmp/x2d-preview "$d/preview-before" || exit 30
# Device-local fallback, independent of host USB connection.
nohup sh -c "sleep 75; sh $d/check.sh restore" > "$d/watchdog.log" 2>&1 < /dev/null &
setprop sys.usb.config none
sleep 1
setprop sys.usb.config "$debug"
i=0
while [ "$(getprop sys.usb.state)" != "$debug" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i+1)); done
[ "$(getprop sys.usb.state)" = "$debug" ] || exit 31
touch "$d/gui-restarted"
stop camera-gui
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 32; fi
start camera-gui
i=0
while [ "$i" -lt 80 ]; do
    /system/bin/odindb-send --print-cmdline -s gui -p osd_clock > "$d/clock.txt" 2>&1
    if grep -q 'E_OSDClock_Top(1)' "$d/clock.txt"; then
        echo STOCK_CLOCK_TOP_OBSERVED > "$d/result"
        echo DEBUG_GUI_VISIBLE > "$d/status"
        break
    fi
    sleep 0.1; i=$((i+1))
done
[ "$i" -lt 80 ] || { echo STOCK_CLOCK_TOP_NOT_OBSERVED > "$d/result"; exit 33; }
# Brief viewing window; no Debug Mode property or AF-C state is written.
sleep 40
