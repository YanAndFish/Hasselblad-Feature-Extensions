#!/bin/sh
set -eu
. /tmp/hbl-x1d-rpa/common.sh
stage=preflight
[ "$#" = 0 ] || die 59
package_check
baseline_check
absent "$s" && absent "$delta" && [ ! -L "$units/victory-gui.service.d" ] || die 63
af_original_files && gui_ready af && gui_idle || die 64
"$d/replay-check" --selftest && "$d/replay-check" --active || die 65
printf '%s\n' replay-af-preflight-ready
