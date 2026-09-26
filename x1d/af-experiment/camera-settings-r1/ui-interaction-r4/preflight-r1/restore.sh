#!/bin/sh
. /tmp/hbl-af-ui-r4/preflight-r1/common.sh
delta_package && regular "$d/touched" && regular "$d/base-gui.dropin" && cmp -s "$gui" "$d/base-gui.dropin" && bus_unchanged || exit 66
paths=$(value victory-gui DropInPaths)
[ "$paths" = "$gui $delta" ] || [ "$paths" = "$gui" ] || exit 66
if ! absent "$delta"; then regular "$delta" && cmp -s "$delta" "$d/95-hbl-af-ui-r4.conf" || exit 66;fi
stop_gui || exit 67
clear_ui_status || exit 67
if ! absent "$delta";then rm "$delta";fi
systemctl daemon-reload
systemctl start victory-gui || exit 68
wait_ready base_ready && bus_unchanged || exit 69
: > "$d/restored"
printf '%s\n' af-ui-r4-previous-af-gui-restored
