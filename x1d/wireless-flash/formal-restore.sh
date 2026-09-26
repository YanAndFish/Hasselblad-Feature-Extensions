#!/bin/sh
# 两阶段恢复：先停发并保留消息消费者，再由电脑确认 FARM 解钩后恢复原服务。
set -eu
umask 077
d=/tmp/hbl-wireless-flash
s=$d/formal-state
gui=/run/systemd/system/victory-gui.service.d/80-hbl-formal-flash.conf
farm=/run/systemd/system/msg2dbus-farm.service.d/80-hbl-formal-flash.conf
p=/sys/module/firmware_class/parameters/path
module=/sys/module/brcmfmac/parameters/firmware_path
mode=${1:-stop}
[ "$#" -le 1 ] || exit 59
case "$mode" in stop|--before-farm-install|--after-farm-unhook) ;; *) exit 59;; esac
[ "$(id -u)" = 0 ] || exit 60
[ -d "$d" ] && [ ! -L "$d" ] && [ "$(stat -c '%u:%a' "$d")" = 0:700 ] || exit 60
[ -d "$s" ] && [ ! -L "$s" ] && [ "$(stat -c '%u:%a' "$s")" = 0:700 ] || exit 60
[ "$(cat "$s/owner")" = formal-linux-install-v1 ] || exit 60
exec 3>&1
exec >> "$d/formal-restore.log" 2>&1
printf 'restore-mode=%s\n' "$mode"
owned_dropins() {
    if [ -f "$s/created-gui-dropin" ]; then [ -f "$gui" ] && [ ! -L "$gui" ] && cmp -s "$gui" "$s/gui.dropin" || return 1; fi
    if [ -f "$s/created-farm-dropin" ]; then [ -f "$farm" ] && [ ! -L "$farm" ] && cmp -s "$farm" "$s/farm.dropin" || return 1; fi
}
owned_dropins || { printf '%s\n' foreign-dropin-change-preserved >&3; exit 61; }
if [ "$mode" = stop ]; then
    [ -f "$s/install-complete" ] && [ -f "$s/created-gui-dropin" ] && [ -f "$s/created-farm-dropin" ] || exit 62
    systemctl stop victory-gui || exit 63
    if systemctl is-active --quiet victory-gui; then exit 63; fi
    if [ -e "$d/formal-stop.request" ] || [ -L "$d/formal-stop.request" ]; then
        [ -f "$d/formal-stop.request" ] && [ ! -L "$d/formal-stop.request" ] &&
        [ "$(stat -c '%u:%a' "$d/formal-stop.request")" = 0:600 ] &&
        [ "$(cat "$d/formal-stop.request")" = stop ] || exit 64
    else
        (set -C; printf 'stop\n' > "$d/formal-stop.request") || exit 64
        chmod 600 "$d/formal-stop.request"
    fi
    for n in 1 2 3 4 5 6 7 8 9 10; do
        state=$(head -n 1 "$d/formal-worker.status" 2>/dev/null || :)
        [ "$state" = formal-worker-stopped-default-off ] && break
        [ "$state" != formal-worker-stop-failed ] || exit 65
        sleep 1
    done
    [ "$(head -n 1 "$d/formal-worker.status")" = formal-worker-stopped-default-off ] || exit 65
    systemctl is-active --quiet msg2dbus-farm || exit 65
    grep -q '^stage=ready meta=1 observe=1$' "$d/formal-observer.status" || exit 65
    pid=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
    case "$pid" in ''|0|*[!0-9]*) exit 65;; esac
    grep -q '/tmp/hbl-wireless-flash/libhbl-formal-observer.so' "/proc/$pid/maps" || exit 65
    grep -q "^master=0 radio-held=0 radio-busy=0 same-process=1 pid=$pid\$" "$d/formal-worker.status" || exit 65
    : > "$s/stop-confirmed"
    printf '%s\n' formal-linux-stopped-observer-retained > "$d/formal-restore.status"
    printf '%s\n' formal-linux-stopped-observer-retained >&3
    exit 0
fi
if [ "$mode" = --after-farm-unhook ]; then
    # 参数由已完成 PC 侧 FARM 原字节读回验证的主任务显式提供。
    [ -f "$s/stop-confirmed" ] || exit 66
fi
if [ -f "$s/radio-mutated" ] && [ ! -f "$s/radio-restored" ]; then
    [ -f "$s/radio-snapshot-complete" ] || exit 67
    [ -f "$s/module-firmware.path" ] && [ -f "$s/firmware-class.path" ] || exit 67
    original=$(cat "$s/module-firmware.path")
    case "$original" in ''|test) ;; *) exit 67;; esac
    if [ -e "$module" ]; then
        current=$(cat "$module")
        if [ -f "$s/radio-original-loaded" ]; then [ "$current" = "$original" ] || exit 67
        elif [ -f "$s/radio-injected" ]; then [ "$current" = test ] || exit 67
        else [ "$current" = "$original" ] || exit 67; fi
    fi
    current=$(cat "$p")
    # 仅本次 radio-mutated 事务可恢复 prepare 退出 trap 尚未清回的临时目录。
    [ "$current" = "$(cat "$s/firmware-class.path")" ] || [ "$current" = "$d" ] || exit 67
    for service in network-manager hostapd; do
        case "$(cat "$s/$service.active")" in active|inactive) ;; *) exit 67;; esac
        unit=$(systemctl show -p LoadState -p ActiveState "$service") || exit 67
        load=$(printf '%s\n' "$unit" | sed -n 's/^LoadState=//p')
        active=$(printf '%s\n' "$unit" | sed -n 's/^ActiveState=//p')
        [ "$load" = loaded ] || exit 67
        case "$active" in active|inactive|failed) ;; *) exit 67;; esac
    done
fi
# 这里仅在未安装 FARM，或主任务已验证解除后执行；不会自行操作 FARM/AF。
if [ -f "$s/created-gui-dropin" ]; then systemctl stop victory-gui || exit 68; fi
if [ -f "$s/created-farm-dropin" ]; then systemctl stop msg2dbus-farm || exit 68; fi
if [ -f "$s/radio-mutated" ] && [ ! -f "$s/radio-restored" ]; then
    systemctl stop network-manager hostapd || exit 69
    if [ ! -f "$s/radio-original-loaded" ]; then
        if [ -e "$module" ]; then rmmod brcmfmac || exit 69; fi
        if [ -s "$s/firmware-class.path" ]; then cat "$s/firmware-class.path" > "$p"; else printf '\000' > "$p"; fi
        [ "$(cat "$p")" = "$(cat "$s/firmware-class.path")" ] || exit 69
        if [ -n "$original" ]; then modprobe brcmfmac firmware_path=test; else modprobe brcmfmac; fi
        [ "$(cat "$module")" = "$original" ] || exit 69
        : > "$s/radio-original-loaded"
    else
        [ -e "$module" ] && [ "$(cat "$module")" = "$original" ] || exit 69
        [ "$(cat "$p")" = "$(cat "$s/firmware-class.path")" ] || exit 69
    fi
    for service in network-manager hostapd; do
        if [ "$(cat "$s/$service.active")" = active ]; then systemctl start "$service"; else systemctl stop "$service"; fi
    done
    : > "$s/radio-restored"
fi
owned_dropins || exit 70
if [ -f "$s/created-gui-dropin" ]; then rm "$gui"; mv "$s/created-gui-dropin" "$s/restored-gui-dropin"; fi
if [ -f "$s/created-farm-dropin" ]; then rm "$farm"; mv "$s/created-farm-dropin" "$s/restored-farm-dropin"; fi
if [ -f "$s/created-gui-directory" ]; then rmdir /run/systemd/system/victory-gui.service.d 2>/dev/null || :; fi
if [ -f "$s/created-farm-directory" ]; then rmdir /run/systemd/system/msg2dbus-farm.service.d 2>/dev/null || :; fi
systemctl daemon-reload
if [ -f "$s/restored-farm-dropin" ]; then systemctl start msg2dbus-farm || exit 71; fi
if [ -f "$s/restored-gui-dropin" ]; then systemctl start victory-gui || exit 71; fi
: > "$s/restore-complete"
printf '%s\n' original-linux-services-and-radio-restored > "$d/formal-restore.status"
printf '%s\n' original-linux-services-and-radio-restored >&3
