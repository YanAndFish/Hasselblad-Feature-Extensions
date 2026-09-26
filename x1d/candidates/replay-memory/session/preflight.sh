#!/bin/sh
set -eu
. /tmp/hbl-x1d-rpm/common.sh
stage=preflight
[ "$#" = 0 ] || die 59
package_check
baseline_check
[ ! -e "$s" ] && [ ! -L "$s" ] || die 63
for role in configstore storage-daemon jpeg-daemon victory-gui; do
    running "$role" "$(base_hash "$role")" && clean_unit "$role" || die 64
done
owners || die 64
"$d/replay-check" --selftest || die 65
"$d/replay-check" --active || die 65
printf '%s\n' replay-preflight-pass
