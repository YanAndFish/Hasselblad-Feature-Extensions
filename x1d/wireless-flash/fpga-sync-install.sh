#!/bin/sh
# 固定 GFS1 临时 Linux 接收链；FARM 钩子由电脑端另行校验和启用。
set -eu
d=/tmp/hbl-wireless-flash
gui=/run/systemd/system/victory-gui.service.d/80-hbl-fpga-sync.conf
farm=/run/systemd/system/msg2dbus-farm.service.d/80-hbl-fpga-sync.conf
worker=/run/systemd/system/hbl-wireless-worker.service
[ -d "$d" ] && [ ! -L "$d" ] || exit 60
[ "$(stat -c '%u:%a' "$d")" = '0:700' ] || exit 60
cd "$d"
sha256sum -c manifest.sha256 >/dev/null || exit 61
[ "$(sha256sum /usr/bin/victory-gui | cut -d' ' -f1)" = d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b ] || exit 62
[ "$(sha256sum /usr/lib/libappscommon.so.1.0.0 | cut -d' ' -f1)" = 2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263 ] || exit 63
[ "$(sha256sum /usr/bin/msg2dbus | cut -d' ' -f1)" = 988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1 ] || exit 63
[ ! -e "$gui" ] && [ ! -e "$farm" ] && [ ! -e "$worker" ] || exit 64
for service in victory-gui msg2dbus-farm; do
    systemctl is-active --quiet "$service" || exit 64
    if systemctl show -p Environment "$service" | grep -q 'LD_PRELOAD='; then exit 64; fi
done
chmod 700 "$d/wireless-worker" "$d/netlink-probe" "$d/farm-sync-hook-check"
HBL_FARM_SYNC_SELFTEST=1 LD_PRELOAD="$d/libhbl-farm-sync-observer.so" "$d/farm-sync-hook-check" || exit 68
"$d/wireless-worker" --check-slots || exit 68
# 这里只准备既有波形；不会调用发射选择器。
if [ "$(/usr/bin/wl phyreg 0 b 2>/dev/null)" != 0x584e ]; then
    sh "$d/prepare-radio.sh" || exit 65
fi
"$d/netlink-probe" || exit 69
rm -f "$d/runtime.status" "$d/worker.status" "$d/worker.sock" "$d/ui.sock" "$d/fpga-sync.sock" "$d/fpga-sync.ready" "$d/sync-observer.status"
cleanup() { sh "$d/fpga-sync-restore.sh" --before-farm-install; }
trap cleanup 0
trap 'exit 72' 1 2 15
printf '%s\n' '[Unit]' 'After=dbus.service msg2dbus-farm.service' '[Service]' \
    'Type=simple' 'ExecStart=/tmp/hbl-wireless-flash/wireless-worker' \
    'ExecStopPost=/bin/sh /tmp/hbl-wireless-flash/release-radio.sh' \
    'Restart=no' 'TimeoutStopSec=3' > "$worker"
systemctl daemon-reload
systemctl start hbl-wireless-worker || exit 70
for n in 1 2 3 4 5; do
    [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] && break
    sleep 1
done
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] || exit 71
[ -S "$d/fpga-sync.sock" ] || exit 71
mkdir -p /run/systemd/system/msg2dbus-farm.service.d
printf '%s\n' '[Service]' 'Environment=HBL_FARM_SYNC_OBSERVE=1' \
    'Environment=LD_PRELOAD=/tmp/hbl-wireless-flash/libhbl-farm-sync-observer.so' > "$farm"
systemctl daemon-reload
systemctl restart msg2dbus-farm || exit 73
for n in 1 2 3 4 5; do
    sleep 1
    systemctl is-active --quiet msg2dbus-farm || continue
    p=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
    case "$p" in ''|0|*[!0-9]*) continue;; esac
    if grep -q '/tmp/hbl-wireless-flash/libhbl-farm-sync-observer.so' "/proc/$p/maps" &&
       grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/sync-observer.status" 2>/dev/null; then break; fi
done
systemctl is-active --quiet msg2dbus-farm || exit 73
p=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
case "$p" in ''|0|*[!0-9]*) exit 73;; esac
grep -q '/tmp/hbl-wireless-flash/libhbl-farm-sync-observer.so' "/proc/$p/maps" || exit 73
grep -q '^stage=ready error=0 .* observe=1 output=1 ' "$d/sync-observer.status" || exit 73
[ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] || exit 73
mkdir -p /run/systemd/system/victory-gui.service.d
printf '%s\n' '[Service]' 'Environment=HBL_RF_ENABLE_PLUGIN=1' \
    'Environment=LD_PRELOAD=/tmp/hbl-wireless-flash/libhbl-wireless.so' > "$gui"
systemctl daemon-reload
systemctl restart victory-gui || exit 74
for n in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] && break
done
[ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] || exit 75
systemctl is-active --quiet hbl-wireless-worker || exit 75
printf '%s\n' 'linux-sync-chain-ready-farm-hook-pending-auto-off' > "$d/fpga-sync.ready"
trap - 0 1 2 15
cat "$d/fpga-sync.ready"
