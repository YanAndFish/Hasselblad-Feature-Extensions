#!/bin/sh
. /tmp/hbl-af-bus-r3/common.sh
base_ready && absent "$delta" && absent "$d/touched" && absent "$d/applied" || exit 61
"$d/bus-local-check" > "$d/local-check.log" 2>&1 || exit 62
pid victory-gui > "$d/gui.pid"
pid msg2dbus-farm > "$d/old-bus.pid"
cp "$farm" "$d/base-farm.dropin"
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
stop_bus || exit 63
(set -C;cat "$d/95-hbl-af-bus-r3.conf" > "$delta") || exit 64
systemctl daemon-reload
systemctl start msg2dbus-farm || exit 65
wait_ready new_ready || exit 66
: > "$d/applied"
printf '%s\n' af-bus-r3-ready
