#!/bin/sh
set -eu
cd /tmp/hbl-wireless-flash/observer
test ! -L /tmp/hbl-wireless-flash/observer
sha256sum -c manifest.sha256 >/dev/null
chmod 700 event-observer
./event-observer --check-slots
test ! -e events.tsv
test ! -e /run/systemd/system/hbl-event-observer.service
cat > /run/systemd/system/hbl-event-observer.service <<'UNIT'
[Unit]
Description=Temporary passive exposure notification observer

[Service]
Type=simple
ExecStart=/tmp/hbl-wireless-flash/observer/event-observer
UMask=0077
Restart=no
TimeoutStopSec=3
UNIT
systemctl daemon-reload
systemctl start hbl-event-observer.service
i=0
while test "$i" -lt 10; do
    if test -f events.tsv && grep -q observer_ready events.tsv; then
        systemctl is-active hbl-event-observer.service
        printf 'observer-ready hardware-actions=0 duration-seconds=300\n'
        exit 0
    fi
    sleep 1
    i=$((i+1))
done
printf 'observer-not-ready\n' >&2
exit 1
