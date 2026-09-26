#!/bin/sh
# 仅恢复本轮有明确所有权的 Linux 文件；FARM/AF 原字节须先由 PC 验证。
. /tmp/hbl-x1d-combined/common.sh
phase=${1:-}
[ "$#" = 1 ] || exit 59
case "$phase" in worker-stop|restore-linux) ;; *) exit 59;; esac
verify_package && owned && owned_dropins || exit 60
if [ "$phase" = worker-stop ]; then
    [ -f "$s/observer.done" ] && absent "$d/formal-stop.request" || exit 61
    held 180000 || exit 61
    (set -C;printf 'stop\n' > "$d/formal-stop.request") || exit 62
    for n in 1 2 3 4 5 6 7 8 9 10; do
        state=$(head -n 1 "$d/formal-worker.status" 2>/dev/null || :)
        [ "$state" = formal-worker-stopped-default-off ] && break
        [ "$state" != formal-worker-stop-failed ] || exit 63
        sleep 1
    done
    [ "$(head -n 1 "$d/formal-worker.status")" = formal-worker-stopped-default-off ] || exit 63
    p=$(pid msg2dbus-farm) || exit 63
    systemctl is-active --quiet msg2dbus-farm && grep -q '^stage=ready meta=1 observe=1$' "$d/formal-observer.status" || exit 63
    grep -q "^master=0 radio-held=0 radio-busy=0 same-process=1 pid=$p\$" "$d/formal-worker.status" || exit 63
    held || exit 63
    : > "$s/worker-stop.done"
    printf '%s\n' combined-worker-stopped-gui-and-consumer-retained
    exit 0
fi
# 未产生 RAM 写入登记，或 PC 已完成本轮逐字恢复验证，方能停止消息消费者。
if [ -e "$s/ram.started" ]; then
    regular "$s/ram-restored.sha256" && [ "$(wc -c < "$s/ram-restored.sha256")" = 65 ] || exit 64
    grep -Eq '^[0-9a-f]{64}$' "$s/ram-restored.sha256" || exit 64
fi
backend=$r/replay-state/backend
if [ -f "$backend/configstore.touched" ] || [ -f "$backend/jpeg-daemon.touched" ]; then
    regular "$backend/restore.done" || exit 64
fi
radio=$d/formal-state
p=/sys/module/firmware_class/parameters/path
module=/sys/module/brcmfmac/parameters/firmware_path
if [ -f "$radio/radio-mutated" ] && [ ! -f "$radio/radio-restored" ]; then
    [ -f "$radio/radio-snapshot-complete" ] && [ -f "$radio/module-firmware.path" ] && [ -f "$radio/firmware-class.path" ] || exit 65
    original=$(cat "$radio/module-firmware.path")
    case "$original" in ''|test) ;; *) exit 65;; esac
    if [ -e "$module" ]; then
        current=$(cat "$module")
        if [ -f "$radio/radio-original-loaded" ]; then [ "$current" = "$original" ] || exit 65
        elif [ -f "$radio/radio-injected" ]; then [ "$current" = test ] || exit 65
        else [ "$current" = "$original" ] || exit 65;fi
    fi
    current=$(cat "$p")
    [ "$current" = "$(cat "$radio/firmware-class.path")" ] || [ "$current" = "$d" ] || exit 65
    for role in network-manager hostapd; do
        case "$(cat "$radio/$role.active")" in active|inactive) ;; *) exit 65;; esac
        [ "$(value "$role" LoadState)" = loaded ] || exit 65
        case "$(value "$role" ActiveState)" in active|inactive|failed) ;; *) exit 65;; esac
    done
fi
if [ -f "$s/farm.touched" ]; then
    systemctl stop msg2dbus-farm || exit 66
    ! systemctl is-active --quiet msg2dbus-farm || exit 66
fi
if [ -f "$radio/radio-mutated" ] && [ ! -f "$radio/radio-restored" ]; then
    systemctl stop network-manager hostapd || exit 67
    if [ ! -f "$radio/radio-original-loaded" ]; then
        if [ -e "$module" ]; then rmmod brcmfmac || exit 67;fi
        if [ -s "$radio/firmware-class.path" ]; then cat "$radio/firmware-class.path" > "$p";else printf '\000' > "$p";fi
        [ "$(cat "$p")" = "$(cat "$radio/firmware-class.path")" ] || exit 67
        if [ -n "$original" ]; then modprobe brcmfmac firmware_path=test;else modprobe brcmfmac;fi
        [ "$(cat "$module")" = "$original" ] || exit 67
        : > "$radio/radio-original-loaded"
    fi
    for role in network-manager hostapd; do
        if [ "$(cat "$radio/$role.active")" = active ]; then systemctl start "$role";else systemctl stop "$role";fi
    done
    : > "$radio/radio-restored"
fi
owned_dropins || exit 68
if [ -f "$s/farm.touched" ]; then
    rm "$farm"
    mv "$s/farm.touched" "$s/farm.restored"
    systemctl daemon-reload
    systemctl start msg2dbus-farm || exit 69
    systemctl is-active --quiet msg2dbus-farm || exit 69
fi
if [ -f "$s/gui.touched" ]; then
    stop_gui || exit 69
    rm "$gui"
    mv "$s/gui.touched" "$s/gui.restored"
    systemctl daemon-reload
    systemctl start victory-gui || exit 69
fi
for role in victory-gui msg2dbus-farm; do clean_service "$role" || exit 70;done
: > "$s/linux-restored.done"
printf '%s\n' combined-original-linux-and-radio-restored
