#!/bin/sh
set -eu
umask 077
. /opt/hbl-four-module-v1/boot-common.sh
if ! verify_package; then exec /usr/bin/victory-gui -platform wayland;fi
n=0
while ! regular "$u/files.ready"; do
    n=$((n+1));[ "$n" -lt 75 ] || exec /usr/bin/victory-gui -platform wayland
    sleep 1
done
private "$u" && private "$d" && private /media/data/hbl-four-module || exit 74
(set -C;printf '%s\n' "$$" >"$u/gui.pid")
exec env HBL_FORMAL_ENABLE_PLUGIN=1 HBL_FORMAL_INSTALL_HOLD=1 HBL_PERSISTENT_SETTINGS=1 HBL_BOOT_LOAD_GUI=1 LD_PRELOAD="$d/libhbl-formal.so" /usr/bin/victory-gui -platform wayland
