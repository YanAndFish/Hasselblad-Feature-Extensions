#!/bin/sh
set -eu
d=/run/hbl-hotspot-ui
p=/opt/hbl-af-only-v1
"$p/authorization-guard" "$p" >/dev/null 2>&1
lib=$p/libhbl-af-ui.so
if test ! -e "$d/embedded-used";then
 (cd "$d" && sha256sum -c manifest.sha256 >/dev/null)
 printf used > "$d/embedded-used"
 lib=$d/libhotspot-entry.so:$lib
fi
printf '%s\n' "$$" > /run/hbl-four-module/gui.pid
export HBL_FORMAL_ENABLE_PLUGIN=1 HBL_FORMAL_INSTALL_HOLD=1
export HBL_PERSISTENT_SETTINGS=1 HBL_BOOT_LOAD_GUI=1
export LD_PRELOAD="$lib"
exec /usr/bin/victory-gui -platform wayland
