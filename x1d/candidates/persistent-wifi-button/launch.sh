#!/bin/sh
# 原厂 GUI 的第一次 ExecStart 直接加载探针；同次开机的后续启动直接用原厂。
set -eu
umask 077
source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
r=/run/hbl-wifi-probe
if ! mkdir -m 700 "$r" 2>/dev/null;then
    exec /usr/bin/victory-gui -platform wayland
fi
if ! (cd "$source" && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null);then
    printf 'verification-failed\n' > "$r/fallback.reason"
    exec /usr/bin/victory-gui -platform wayland
fi
if ! cp "$source/libhbl-wifi-probe.so" "$source/button.rcc" "$source/health" "$r/";then
    printf 'runtime-copy-failed\n' > "$r/fallback.reason"
    exec /usr/bin/victory-gui -platform wayland
fi
chmod 700 "$r/health"
sh "$source/monitor.sh" "$$" > "$r/monitor.log" 2>&1 &
exec env HBL_WIFI_PROBE=1 LD_PRELOAD="$r/libhbl-wifi-probe.so" /usr/bin/victory-gui -platform wayland
