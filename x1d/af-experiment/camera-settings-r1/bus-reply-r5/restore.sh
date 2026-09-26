#!/bin/sh
. /tmp/hbl-af-bus-r5/common.sh
delta_package && absent "$d/restored" && regular "$d/touched" && regular "$d/base-farm.dropin" && cmp -s "$farm" "$d/base-farm.dropin" || exit 67
regular "$d/gui.pid" && [ "$(pid victory-gui)" = "$(cat "$d/gui.pid")" ] || exit 67
paths=$(value msg2dbus-farm DropInPaths)
[ "$paths" = "$farm $previous_delta $delta" ] || [ "$paths" = "$farm $previous_delta" ] || exit 67
if ! absent "$delta";then regular "$delta" && cmp -s "$delta" "$d/96-hbl-af-bus-r5.conf" || exit 67;fi
stop_bus || exit 68
if ! absent "$delta";then rm "$delta";fi
systemctl daemon-reload
systemctl start msg2dbus-farm || exit 69
wait_ready old_ready && gui_same || exit 70
: > "$d/restored"
printf '%s\n' af-bus-r5-previous-bus-restored
