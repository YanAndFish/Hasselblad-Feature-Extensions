#!/bin/sh
# 移除本模块的临时 GUI 覆盖；相机断电也会清除这些 tmpfs 内容。
set -eu
drop=/run/systemd/system/victory-gui.service.d/80-hbl-wireless.conf
worker=/run/systemd/system/hbl-wireless-worker.service
if [ -f "$worker" ]; then
    systemctl stop hbl-wireless-worker || true
    rm -f "$worker"
    systemctl daemon-reload
fi
if [ -f "$drop" ]; then
    rm -f "$drop"
    systemctl daemon-reload
    systemctl restart victory-gui
fi
# 仅对本模块版本释放预先准备时持有的 MAC，避免 GUI 异常退出遗留占用。
marker=$(/usr/bin/wl phyreg 0 b 2>/dev/null || true)
if [ "$marker" = 0x584e ] || [ "$marker" = 0x584d ]; then
    /usr/bin/wl phyreg 27 b >/dev/null 2>&1 || true
fi
printf '%s\n' 'original-gui-restored'
