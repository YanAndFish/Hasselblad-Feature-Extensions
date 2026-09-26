#!/bin/sh
set -eu
. /tmp/hbl-x1d-rpa/common.sh
stage=arguments
[ "$#" = 0 ] || die 59
sh "$d/preflight.sh" || die 64
mkdir -m 700 "$s"
printf '%s\n' x1d-replay-session-v1 > "$s/owner"
sha256sum "$d/manifest.sha256" | cut -d' ' -f1 > "$s/package.sha256"
protect_snapshot > "$s/protection.before" || die 65
finish() {
    result=$?;trap - 0 1 2 15
    if [ "$result" != 0 ]; then
        printf 'replay-af-install-failed stage=%s exit=%s\n' "$stage" "$result" > "$s/install.status"
        if sh "$d/restore.sh"; then printf '%s\n' replay-af-rollback-complete;else printf '%s\n' replay-af-rollback-incomplete;fi
    fi
    exit "$result"
}
trap finish 0
trap 'exit 72' 1 2 15
stage=begin-independent-hold
"$d/replay-check" --begin || die 65
protection_unchanged && gui_ready af || die 64
stage=stop-af-gui
stop_owned_gui || die 66
protection_unchanged && absent "$delta" || die 68
stage=add-gui-delta
: > "$s/delta-intent"
(set -C;cat "$d/delta.conf" > "$delta") || die 68
systemctl daemon-reload
stage=start-combined-gui
systemctl start victory-gui || die 66
stage=combined-gui-health
wait_health combined || die 67
protection_unchanged || die 69
: > "$s/enabled"
: > "$s/release"
stage=release-independent-hold
"$d/replay-check" --active && protection_unchanged && gui_ready combined || die 69
printf '%s\n' replay-af-loaded-awaiting-functional-validation > "$s/install.status"
trap - 0 1 2 15
cat "$s/install.status"
