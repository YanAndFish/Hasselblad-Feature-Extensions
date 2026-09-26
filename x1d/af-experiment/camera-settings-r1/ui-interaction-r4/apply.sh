#!/bin/sh
. /tmp/hbl-af-ui-r4/common.sh
base_ready && absent "$delta" && absent "$d/applied" && absent "$d/touched" || exit 61
pid msg2dbus-farm > "$d/bus.pid"
cp "$gui" "$d/base-gui.dropin"
sha256sum "$gui" > "$d/base-gui.sha256"
rollback_on_failure() {
    code=$?;trap - 0 1 2 15
    if [ "$code" != 0 ] && [ -f "$d/touched" ];then
        if sh "$d/restore.sh" > "$d/failure-restore.log" 2>&1;then printf restored > "$d/failure-restored";else printf unknown > "$d/failure-restore-unknown";fi
    fi
    exit "$code"
}
trap rollback_on_failure 0
trap 'exit 72' 1 2 15
: > "$d/touched"
stop_gui || exit 62
clear_ui_status || exit 62
(set -C;cat "$d/95-hbl-af-ui-r4.conf" > "$delta") || exit 63
systemctl daemon-reload
systemctl start victory-gui || exit 64
wait_ready r4_ready || exit 65
: > "$d/applied"
printf '%s\n' af-ui-r4-ready
