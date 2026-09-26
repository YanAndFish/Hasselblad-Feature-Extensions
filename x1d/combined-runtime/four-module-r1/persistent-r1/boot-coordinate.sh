#!/bin/sh
set -eu
umask 077
. /opt/hbl-four-module-v1/boot-common.sh
private "$u" && private "$d"
(set -C;printf started >"$u/coordinator.started")
completed=0
phase=wait-gui
finish() {
    rc=$?
    trap - 0 1 2 15
    if [ "$completed" = 0 ];then
        printf '%s\n' "startup-failed-$rc phase=$phase" >"$u/boot-failed"
        # 未知的内存执行/写入绝不通过自动服务重启来重放。
        printf '%s\n' "startup-failed-$rc phase=$phase" >/media/data/hbl-four-module/startup-failure.status
    fi
    exit "$rc"
}
trap finish 0
trap 'exit 79' 1 2 15
gui_ready() {
    regular "$u/gui.pid" || return 1
    g=$(cat "$u/gui.pid")
    case "$g" in ''|0|*[!0-9]*) return 1;; esac
    [ "$(systemctl show -p MainPID victory-gui)" = "MainPID=$g" ] || return 1
    [ "$(cat "$u/ui.status" 2>/dev/null || true)" = "ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1 pid=$g" ] || return 1
    [ "$(cat "$u/replay.status" 2>/dev/null || true)" = "replay-page-ready-resources7-components7-pages2 pid=$g" ] || return 1
    [ "$(cat "$d/formal-runtime.status" 2>/dev/null || true)" = formal-ui-loaded-default-off ] || return 1
    "$d/formal-system-check" --require-held-min-ms 300000 >/dev/null
}
n=0
while ! gui_ready;do n=$((n+1));[ "$n" -lt 110 ] || exit 80;sleep 1;done
f=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
case "$f" in ''|0|*[!0-9]*) exit 81;;esac
[ "$(cat "$d/formal-worker.status")" = "formal-worker-ready-default-off
master=0 radio-held=0 radio-busy=0 same-process=1 pid=$f" ] || exit 81
# native 保留旧未完成标记，只在完整原厂前检通过后允许写入。
phase=prepare-radio
sh "$d/formal-prepare-radio.sh"
phase=netlink-check
"$d/formal-netlink-probe"
gui_ready
phase=load-modules
(set -C;printf 'HBL1 %s\n' "$g" >"$u/load.request")
n=0
while :;do
    status=$(cat "$u/boot-loader.status" 2>/dev/null || true)
    case "$status" in 'state=ready phase=modules-ready '*)break;;state=failed*|state=blocked*)exit 83;;esac
    n=$((n+1));[ "$n" -lt 390 ] || exit 84;sleep 1
done
[ "$(systemctl show -p MainPID msg2dbus-farm)" = "MainPID=$f" ] || exit 85
gui_ready
phase=enable-controls
(set -C;printf ready >"$d/formal-enable.ready")
n=0
while [ "$(cat "$d/formal-enable.confirmed" 2>/dev/null || true)" != ready ];do
    n=$((n+1));[ "$n" -lt 15 ] || exit 86;sleep 1
done
gui_ready
phase=restore-settings
(set -C;printf release >"$d/formal-state/hold.release")
n=0
while [ "$(cat "$u/settings-restore.status" 2>/dev/null || true)" != "HPR1 $g ready" ];do
    case "$(cat "$u/settings-restore.status" 2>/dev/null || true)" in *failed)exit 87;;esac
    n=$((n+1));[ "$n" -lt 15 ] || exit 88;sleep 1
done
printf 'ready\n' >"$u/boot.ready.next"
mv "$u/boot.ready.next" "$u/boot.ready"
printf '%s\n' four-modules-loaded >"$u/result"
completed=1
