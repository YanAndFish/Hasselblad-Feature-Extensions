#!/bin/sh
set -eu
d=/run/hbl-hotspot-test
i=wlp1s0
case "$1" in
start)
  test -s "$d/wpa.conf"
  test ! -e "$d/start.sent"
  printf sent >"$d/start.sent"
  systemctl stop network-manager
  systemctl stop hostapd
  ip link set "$i" down
  iw dev "$i" set type managed
  ip link set "$i" up
  /usr/sbin/wpa_supplicant -D nl80211 -i "$i" -c "$d/wpa.conf" < /dev/null >"$d/wpa.log" 2>&1 &
  p=$!
  printf '%s\n' "$p" >"$d/wpa.pid"
  sleep 1
  kill -0 "$p"
  printf client-started
  ;;
dhcp)
  test ! -e "$d/dhcp.sent"
  printf sent >"$d/dhcp.sent"
  /sbin/udhcpc -f -n -q -t 4 -T 3 -i "$i" -s "$d/dhcp.sh" >"$d/dhcp.log" 2>&1
  test -s "$d/bound"
  printf address-acquired
  ;;
restore)
  if test -f "$d/wpa.pid";then
    p=$(cat "$d/wpa.pid")
    case "$p" in ''|*[!0-9]*)exit 5;;esac
    if test -e "/proc/$p/cmdline";then
      tr '\000' ' ' <"/proc/$p/cmdline" | grep -F "$d/wpa.conf" >/dev/null
      kill "$p"
      n=0;while test -e "/proc/$p" && test "$n" -lt 20;do sleep 0.1;n=$((n+1));done
      test ! -e "/proc/$p"
    fi
  fi
  ip addr flush dev "$i"
  ip link set "$i" down
  iw dev "$i" set type managed
  systemctl start network-manager
  systemctl start hostapd
  rm -f "$d/wpa.conf"
  printf original-services-started
  ;;
*)exit 2;;
esac
