#!/bin/sh
# GUI 与 observer 协议成对更新；不重写 FARM、AF 或无线固件。
set -eu
umask 077
d=/tmp/hbl-wireless-flash
u=/tmp/hbl-calibration-r1
c=/run/hbl-four-module
cd "$u"
sha256sum -c update.sha256 >/dev/null
[ "$(id -u)" = 0 ]
for p in "$d" "$u" "$c"; do
 [ -d "$p" ] && [ ! -L "$p" ] && [ "$(stat -c '%u:%a' "$p")" = 0:700 ]
done
[ "$(sha256sum "$d/manifest.sha256" | cut -d' ' -f1)" = e52e3304080bee4e6767137d18498e9c289d6317bfa962e7fc1e44d2766b00ab ]
(cd "$d" && sha256sum -c manifest.sha256 >/dev/null)
[ -f "$d/formal-state/install-complete" ] && [ -f "$d/formal-state/hold.release" ]
[ -f "$d/formal-enable.ready" ] && [ -f "$d/formal-enable.confirmed" ]
[ "$(cat "$d/formal-stop.request")" = stop ]
cmp "$d/formal-ui.rcc" "$c/combined-ui.rcc"
"$d/formal-system-check" --require-ui-stage > health-before
HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD="$u/libhbl-formal-observer.so" "$d/formal-sync-hook-check" > selfcheck
grep -q '^sync-hook-selftest: own=10 forwarded=.* status=1 hardware=0$' selfcheck
systemctl is-active --quiet victory-gui msg2dbus-farm
oldpid=$(systemctl show -p MainPID victory-gui | cut -d= -f2)
oldfarm=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
[ -d previous ] && [ ! -L previous ]
for name in formal-ui.rcc libhbl-formal.so libhbl-formal-observer.so manifest.sha256; do cmp "previous/$name" "$d/$name"; done
cmp previous/package-manifest.sha256 "$d/formal-state/package-manifest.sha256"
expected=$(printf 'formal-worker-stopped-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=%s' "$oldfarm")
[ "$(cat "$d/formal-worker.status")" = "$expected" ]
stopped=0
changed=0
rollback() {
 code=$?
 trap - 0 1 2 15
 if [ "$code" != 0 ] && [ "$stopped" = 1 ]; then
  systemctl stop victory-gui || exit 69
  systemctl stop msg2dbus-farm || exit 69
  if [ "$changed" = 1 ]; then
   cp previous/formal-ui.rcc previous/libhbl-formal.so previous/libhbl-formal-observer.so previous/manifest.sha256 "$d/" || exit 69
   cp previous/formal-ui.rcc "$c/combined-ui.rcc" || exit 69
   cp previous/package-manifest.sha256 "$d/formal-state/package-manifest.sha256" || exit 69
  fi
  for flag in formal-stop.request formal-enable.ready formal-enable.confirmed; do
   if [ -e "$d/$flag" ]; then mv "$d/$flag" "$u/failed-$flag" || exit 69; fi
  done
  systemctl start msg2dbus-farm || exit 69
  systemctl start victory-gui || exit 69
  printf ready > "$d/formal-enable.ready" || exit 69
  printf '%s\n' calibration-update-failed-previous-pair-restored > result
 fi
 exit "$code"
}
trap rollback 0
trap 'exit 68' 1 2 15
stopped=1
systemctl stop victory-gui
systemctl stop msg2dbus-farm
[ "$(systemctl show -p MainPID victory-gui)" = MainPID=0 ]
[ "$(systemctl show -p MainPID msg2dbus-farm)" = MainPID=0 ]
changed=1
cp formal-ui.rcc libhbl-formal.so libhbl-formal-observer.so manifest.sha256 "$d/"
cp formal-ui.rcc "$c/combined-ui.rcc"
cp package-manifest.sha256 "$d/formal-state/package-manifest.sha256"
(cd "$d" && sha256sum -c manifest.sha256 >/dev/null)
for flag in formal-stop.request formal-enable.ready formal-enable.confirmed; do mv "$d/$flag" "previous/$flag"; done
systemctl start msg2dbus-farm
farm=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
case "$farm" in ''|0|*[!0-9]*) exit 66;; esac
[ "$farm" != "$oldfarm" ]
expected=$(printf 'formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=%s' "$farm")
n=0
while [ "$n" -lt 30 ]; do
 [ "$(cat "$d/formal-worker.status")" = "$expected" ] && [ "$(cat "$d/formal-observer.status")" = 'stage=ready meta=1 observe=1' ] && break
 n=$((n+1)); sleep 1
done
[ "$(cat "$d/formal-worker.status")" = "$expected" ]
[ "$(cat "$d/formal-observer.status")" = 'stage=ready meta=1 observe=1' ]
grep -q /tmp/hbl-wireless-flash/libhbl-formal-observer.so "/proc/$farm/maps"
systemctl start victory-gui
pid=$(systemctl show -p MainPID victory-gui | cut -d= -f2)
case "$pid" in ''|0|*[!0-9]*) exit 66;; esac
[ "$pid" != "$oldpid" ]
ready() {
 [ "$(cat "$d/formal-runtime.status" 2>/dev/null)" = formal-ui-loaded-default-off ] &&
 [ "$(cat "$c/ui.status" 2>/dev/null)" = "ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1 pid=$pid" ] &&
 [ "$(cat "$c/replay.status" 2>/dev/null)" = "replay-page-ready-resources7-components7-pages2 pid=$pid" ]
}
n=0
while [ "$n" -lt 110 ]; do ready && break; n=$((n+1)); sleep 1; done
ready
[ "$(systemctl show -p MainPID victory-gui)" = "MainPID=$pid" ]
[ "$(systemctl show -p MainPID msg2dbus-farm)" = "MainPID=$farm" ]
grep -q /tmp/hbl-wireless-flash/libhbl-formal.so "/proc/$pid/maps"
[ -S "$d/formal-ui.sock" ] && [ -S "$d/formal-worker.sock" ]
"$d/formal-system-check" --require-ui-stage > health-after
(set -C; printf ready > "$d/formal-enable.ready")
n=0
while [ "$n" -lt 30 ]; do
 [ "$(cat "$d/formal-enable.confirmed" 2>/dev/null)" = ready ] && break
 n=$((n+1)); sleep 1
done
[ "$(cat "$d/formal-enable.confirmed")" = ready ]
systemctl is-active --quiet victory-gui msg2dbus-farm
printf '%s\n' calibration-increment-ready > result
trap - 0 1 2 15
