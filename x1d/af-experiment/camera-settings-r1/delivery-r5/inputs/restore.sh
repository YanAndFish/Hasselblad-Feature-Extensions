#!/bin/sh
# 有 RAM 写入后，必须先完成本次 AF 日志对应的逐字恢复证明。
. /tmp/hbl-x1d-combined/common.sh
[ "$#" = 1 ] && [ "$1" = restore-linux ] || exit 59
verify_package || exit 60
# Linux 阶段早退且尚未触及服务时，仅确认原厂基线；不清理未知目录。
if absent "$s/ram.started" && absent "$gui" && absent "$farm" && clean_service victory-gui && clean_service msg2dbus-farm;then
    printf '%s\n' af-only-original-linux-restored;exit 0
fi
owned && owned_dropins || exit 60
if [ -e "$s/ram.started" ]; then
    regular "$s/ram-restored.sha256" && [ "$(wc -c < "$s/ram-restored.sha256")" = 65 ] || exit 64
    grep -Eq '^[0-9a-f]{64}$' "$s/ram-restored.sha256" || exit 64
fi
if [ -f "$s/farm.touched" ]; then
    systemctl stop msg2dbus-farm || exit 66
    ! systemctl is-active --quiet msg2dbus-farm || exit 66
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
printf '%s\n' af-only-original-linux-restored
