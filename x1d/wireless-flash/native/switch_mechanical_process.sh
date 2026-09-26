#!/bin/sh
# 两种处理程序互斥切换。界面须先确认自动关闭、无待发且无线已释放。
set -eu
d=/tmp/hbl-wireless-flash
case "${1:-}" in 0|1) mode=$1;; *) exit 64;; esac
[ "$#" = 1 ] || exit 64
[ -d "$d" ] && [ ! -L "$d" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] || exit 60
mkdir "$d/process-switch.lock" || exit 61
cleanup() {
    result=$?
    if [ "$result" != 0 ]; then
        # 失败时保持自动关闭，并恢复原消息服务，避免影响相机正常消息收发。
        systemctl stop hbl-wireless-worker || true
        printf '0\n' > "$d/process-mode"
        systemctl restart msg2dbus-farm || true
    fi
    rmdir "$d/process-switch.lock"
    exit "$result"
}
trap cleanup 0
trap 'exit 72' 1 2 15
cd "$d"
sha256sum -c manifest.sha256 >/dev/null || exit 62
systemctl stop hbl-wireless-worker
systemctl stop msg2dbus-farm
# 即使进程退出未走 C++ 析构，也必须明确配对释放后才能启用另一程序。
[ "$(/usr/bin/wl phyreg 0 b)" = 0x5851 ] || exit 63
released=$(/usr/bin/wl phyreg 27 b)
case "$released" in 0x0001|0x1) ;; *) exit 63;; esac
rm -f "$d/worker.sock" "$d/mechanical-sync.sock" "$d/worker.status" "$d/mechanical-observer.status"
printf '%s\n' "$mode" > "$d/process-mode.next"
mv -f "$d/process-mode.next" "$d/process-mode"
systemctl start msg2dbus-farm
if [ "$mode" = 0 ]; then
    systemctl start hbl-wireless-worker
    for n in 1 2 3 4 5; do
        [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] && break
        sleep 1
    done
    [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] || exit 65
    systemctl restart msg2dbus-farm
fi
for n in 1 2 3 4 5; do
    sleep 1
    [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] &&
        grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status" && break
done
systemctl is-active --quiet msg2dbus-farm
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ]
grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/mechanical-observer.status"
if [ "$mode" = 1 ]; then
    if systemctl is-active --quiet hbl-wireless-worker; then exit 66; fi
else
    systemctl is-active --quiet hbl-wireless-worker
fi
printf 'process-mode=%s ready-default-off\n' "$mode"
