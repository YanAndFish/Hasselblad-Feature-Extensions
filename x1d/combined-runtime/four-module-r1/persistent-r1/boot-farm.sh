#!/bin/sh
set -eu
umask 077
. /opt/hbl-four-module-v1/boot-common.sh
if ! verify_package; then exec /usr/bin/msg2dbus -u /dev/ttymxc2 -b 921600 --role farm;fi
# 同次开机不重复装载，也不沿用上个进程的内存归属。
absent "$u" && absent "$d" || exit 71
mkdir -m 700 "$u" "$d"
n=0
while ! data_ready; do
    n=$((n+1));[ "$n" -lt 60 ] || { printf data-mount-missing >"$u/boot-failed";exit 72; }
    sleep 1
done
if absent /media/data/hbl-four-module;then mkdir -m 700 /media/data/hbl-four-module;fi
private /media/data/hbl-four-module || exit 73
cp -R "$p/runtime/." "$d/"
cp "$p/combined-ui.rcc" "$d/formal-ui.rcc"
(cd "$d" && sha256sum -c manifest.sha256 >/dev/null)
cp "$p/combined-ui.rcc" "$u/combined-ui.rcc"
chmod 700 "$d/boot-wait" "$d/formal-client-check" "$d/formal-sync-hook-check" "$d/formal-netlink-probe" "$d/formal-system-check"
mkdir -m 700 "$d/formal-state"
printf '%s\n' formal-linux-install-v1 >"$d/formal-state/owner"
awk '{printf "HHD1 %.0f\n",int($1*1000)+1200000}' /proc/uptime >"$d/formal-state/hold.deadline"
printf ready >"$u/files.ready"
sh "$p/boot-coordinate.sh" >"$u/coordinator.log" 2>&1 &
exec env HBL_FORMAL_SYNC_OBSERVE=1 HBL_BOOT_LOAD=1 LD_PRELOAD="$d/libhbl-formal-observer.so" /usr/bin/msg2dbus -u /dev/ttymxc2 -b 921600 --role farm
