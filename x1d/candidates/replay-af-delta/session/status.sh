#!/bin/sh
set -eu
. /tmp/hbl-x1d-rpa/common.sh
stage=status
[ "$#" = 0 ] || die 59
package_check
state_check
protection_unchanged || die 73
mode=combined
[ ! -f "$s/restored" ] || mode=af
gui_ready "$mode" && "$d/replay-check" --active || die 74
printf 'replay-af-status mode=%s protected=1\n' "$mode"
