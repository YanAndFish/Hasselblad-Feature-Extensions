#!/bin/sh
set -eu
. /tmp/hbl-x1d-rpa/common.sh
stage=restore-to-af
[ "$#" = 0 ] || die 59
package_check
state_check
protection_unchanged || die 73
if [ -f "$s/restored" ]; then gui_ready af && "$d/replay-check" --active || die 74;printf '%s\n' replay-af-restored;exit 0;fi
if ! absent "$delta"; then
    [ -f "$s/delta-intent" ] && regular "$delta" && cmp -s "$delta" "$d/delta.conf" || die 73
fi
: > "$s/restore-started"
: > "$s/release"
if [ -f "$s/gui-stop-intent" ]; then
    stop_owned_gui || die 74
    protection_unchanged || die 73
    if [ -f "$delta" ]; then rm "$delta";fi
    systemctl daemon-reload
    systemctl start victory-gui || die 74
    wait_health af || die 74
else
    absent "$delta" && gui_ready af && "$d/replay-check" --active || die 74
fi
protection_unchanged || die 73
: > "$s/restored"
printf '%s\n' replay-af-restored > "$s/restore.status"
cat "$s/restore.status"
