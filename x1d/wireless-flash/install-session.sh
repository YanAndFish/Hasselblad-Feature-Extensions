#!/bin/sh
# 仅安装本次临时会话。这里不触发相机拍摄，也不调用试闪选择器。
set -eu
d=/tmp/hbl-wireless-flash
drop=/run/systemd/system/victory-gui.service.d/80-hbl-wireless.conf
worker=/run/systemd/system/hbl-wireless-worker.service
[ -d "$d" ] && [ -f "$d/manifest.sha256" ] || exit 60
cd "$d"
sha256sum -c manifest.sha256 >/dev/null || exit 61
[ "$(sha256sum /usr/bin/victory-gui | cut -d' ' -f1)" = d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b ] || exit 62
[ "$(sha256sum /usr/lib/libappscommon.so.1.0.0 | cut -d' ' -f1)" = 2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263 ] || exit 63
[ ! -e "$drop" ] || exit 64
[ ! -e "$worker" ] || exit 64
chmod 700 "$d/wireless-worker" "$d/netlink-probe"
"$d/wireless-worker" --check-slots || exit 68
# 无线加载器仅恢复已经核对过的临时 WLTEST 波形与增益，不发射。
if [ "$(/usr/bin/wl phyreg 0 b 2>/dev/null)" != 0x584e ]; then
    sh "$d/prepare-radio.sh" || exit 65
fi
"$d/netlink-probe" || exit 69
rm -f "$d/runtime.status"
rm -f "$d/worker.status" "$d/worker.sock" "$d/ui.sock"
printf '%s\n' '[Unit]' 'After=dbus.service msg2dbus-farm.service' '[Service]' \
  'Type=simple' 'ExecStart=/tmp/hbl-wireless-flash/wireless-worker' \
  'ExecStopPost=/bin/sh /tmp/hbl-wireless-flash/release-radio.sh' \
  'Restart=no' 'TimeoutStopSec=3' > "$worker"
systemctl daemon-reload
if ! systemctl start hbl-wireless-worker; then
    sh "$d/restore-session.sh"
    exit 70
fi
for n in 1 2 3 4 5; do
    [ "$(cat "$d/worker.status" 2>/dev/null)" = worker-ready-default-off ] && break
    sleep 1
done
if [ "$(cat "$d/worker.status" 2>/dev/null)" != worker-ready-default-off ]; then
    sh "$d/restore-session.sh"
    exit 71
fi
mkdir -p /run/systemd/system/victory-gui.service.d
printf '%s\n' '[Service]' 'Environment=HBL_RF_ENABLE_PLUGIN=1' \
  'Environment=LD_PRELOAD=/tmp/hbl-wireless-flash/libhbl-wireless.so' > "$drop"
systemctl daemon-reload
if ! systemctl restart victory-gui; then
    sh "$d/restore-session.sh"
    exit 66
fi
for n in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    [ "$(cat "$d/runtime.status" 2>/dev/null)" = ui-loaded-worker-default-off ] && break
done
if [ "$(cat "$d/runtime.status" 2>/dev/null)" != ui-loaded-worker-default-off ]; then
    sh "$d/restore-session.sh"
    printf '%s\n' 'gui-restored-runtime-not-ready'
    exit 67
fi
printf '%s\n' 'ui-loaded-worker-default-off'
