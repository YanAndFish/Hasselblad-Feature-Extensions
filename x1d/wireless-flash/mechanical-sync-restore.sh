#!/bin/sh
# 默认仅停引闪/恢复界面，保留 GMS1 消息消费直到 FARM 钩子已解除。
set -eu
d=/tmp/hbl-wireless-flash
gui=/run/systemd/system/victory-gui.service.d/80-hbl-mechanical-sync.conf
farm=/run/systemd/system/msg2dbus-farm.service.d/80-hbl-mechanical-sync.conf
worker=/run/systemd/system/hbl-wireless-worker.service
mode=${1:-stop}
case "$mode" in stop|--before-farm-install|--after-farm-unhook) ;; *) exit 64;; esac
if [ -f "$worker" ]; then
    systemctl stop hbl-wireless-worker || exit 70
    rm -f "$worker"
    systemctl daemon-reload
fi
rm -f "$d/mechanical-sync.ready"
if [ -f "$gui" ]; then
    rm -f "$gui"
    systemctl daemon-reload
    systemctl restart victory-gui || exit 71
fi
sh "$d/release-radio.sh"
if [ "$mode" = stop ]; then
    printf '%s\n' 'flash-stopped-gui-restored-sync-consumer-retained'
    exit 0
fi
# 此分支只能在尚未装入 FARM 钩子或电脑已验证解除之后使用。
if [ -f "$farm" ]; then
    rm -f "$farm"
    systemctl daemon-reload
    systemctl restart msg2dbus-farm || exit 72
fi
printf '%s\n' 'original-gui-and-farm-service-restored'
