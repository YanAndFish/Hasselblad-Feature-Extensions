#!/bin/sh
set -eu
umask 077
d=/tmp/hbl-wireless-flash
u=/tmp/hbl-evf-hint-r1
c=/run/hbl-four-module
cd "$u"
sha256sum -c update.sha256 >/dev/null
[ "$(id -u)" = 0 ]
for p in "$d" "$u" "$c"; do
 [ -d "$p" ] && [ ! -L "$p" ] && [ "$(stat -c '%u:%a' "$p")" = 0:700 ]
done
[ "$(sha256sum "$d/manifest.sha256" | cut -d' ' -f1)" = 61ffd1f1ba51acee1209aa0d5d10cd25a700e4a2189114f0dded5462d0547869 ]
(cd "$d" && sha256sum -c manifest.sha256 >/dev/null)
[ -f "$d/formal-state/install-complete" ] && [ -f "$d/formal-state/hold.release" ]
[ ! -e "$d/formal-stop.request" ]
cmp "$d/formal-ui.rcc" "$c/combined-ui.rcc"
"$d/formal-system-check" --require-ui-stage > "$u/health-before"
systemctl is-active --quiet victory-gui msg2dbus-farm
oldpid=$(systemctl show -p MainPID victory-gui | cut -d= -f2)
farmpid=$(systemctl show -p MainPID msg2dbus-farm | cut -d= -f2)
[ ! -e previous ] && mkdir -m 700 previous
cp "$d/formal-ui.rcc" "$d/libhbl-formal.so" "$d/manifest.sha256" previous/
cp "$d/formal-state/package-manifest.sha256" previous/package-manifest.sha256
stopped=0
changed=0
rollback() {
 code=$?
 trap - 0 1 2 15
 if [ "$code" != 0 ] && [ "$stopped" = 1 ]; then
  systemctl stop victory-gui || exit 69
  if [ "$changed" = 1 ]; then
   cp previous/formal-ui.rcc previous/libhbl-formal.so previous/manifest.sha256 "$d/" || exit 69
   cp previous/formal-ui.rcc "$c/combined-ui.rcc" || exit 69
   cp previous/package-manifest.sha256 "$d/formal-state/package-manifest.sha256" || exit 69
  fi
  systemctl start victory-gui || exit 69
  printf '%s\n' evf-update-failed-previous-resources-restored > result
 fi
 exit "$code"
}
trap rollback 0
trap 'exit 68' 1 2 15
stopped=1
systemctl stop victory-gui
[ "$(systemctl show -p MainPID victory-gui)" = MainPID=0 ]
sleep 3
systemctl is-active --quiet msg2dbus-farm
[ "$(systemctl show -p MainPID msg2dbus-farm)" = "MainPID=$farmpid" ]
changed=1
cp formal-ui.rcc libhbl-formal.so manifest.sha256 "$d/"
cp formal-ui.rcc "$c/combined-ui.rcc"
cp package-manifest.sha256 "$d/formal-state/package-manifest.sha256"
(cd "$d" && sha256sum -c manifest.sha256 >/dev/null)
mv "$d/formal-runtime.status" previous/runtime.status
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
[ "$(systemctl show -p MainPID msg2dbus-farm)" = "MainPID=$farmpid" ]
grep -q /tmp/hbl-wireless-flash/libhbl-formal.so "/proc/$pid/maps"
[ -S "$d/formal-ui.sock" ] && [ -S "$d/formal-worker.sock" ]
"$d/formal-system-check" --require-ui-stage > health-after
printf '%s\n' evf-hint-increment-ready > result
trap - 0 1 2 15
