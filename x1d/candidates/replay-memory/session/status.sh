#!/bin/sh
set -eu
. /tmp/hbl-x1d-rpm/common.sh
stage=status
[ "$#" = 0 ] || die 59
package_check
state_check
mode=staged
[ ! -f "$s/enabled" ] || mode=enabled
[ ! -f "$s/restored" ] || mode=restored
health=unavailable
if "$d/replay-check" --active >/dev/null 2>&1 && owners >/dev/null 2>&1; then health=active; fi
services=match
for role in configstore jpeg-daemon victory-gui; do
    expected=$(base_hash "$role")
    if ! running "$role" "$expected"; then services=mismatch; fi
done
printf 'replay-status recorded=%s live-health=%s live-services=%s\n' "$mode" "$health" "$services"
