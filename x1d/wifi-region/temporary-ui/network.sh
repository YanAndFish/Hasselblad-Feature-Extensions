#!/bin/sh
set -eu
d=/run/hbl-hotspot-ui
test "$(id -u)" = 0
test -d "$d" && test ! -L "$d"
case "$1" in
start)
 test "$(cat /run/hbl-four-module/radio-mode/driver)" = factory
 ! systemctl is-active --quiet network-manager
 ! systemctl is-active --quiet hostapd
 test "$(dbus-send --system --print-reply --reply-timeout=2000 --dest=com.hasselblad.config /config org.freedesktop.DBus.Properties.Get string:com.hasselblad.config string:WIFI_power | sed -n 's/.*boolean \(true\|false\).*/\1/p')" = false
 test ! -e "$d/started"
 test -z "$(/sbin/ip -4 addr show dev wlp1s0 | sed -n '/inet /p')"
 /usr/bin/wl band > "$d/band"
 /usr/bin/wl infra > "$d/infra"
 /usr/bin/wl ap > "$d/ap"
 /usr/bin/wl isup > "$d/up"
 touch "$d/started"
 /usr/bin/wl down
 /usr/bin/wl ap 0
 /usr/bin/wl infra 1
 /usr/bin/wl band auto
 /usr/bin/wl scansuppress 0
 /usr/bin/wl up
 printf 'ctrl_interface=%s/ctrl\nupdate_config=0\n' "$d" > "$d/wpa.conf"
 /usr/sbin/wpa_supplicant -D nl80211 -i wlp1s0 -c "$d/wpa.conf" </dev/null >"$d/wpa.log" 2>&1 &
 echo $! > "$d/wpa.pid"
 n=0;until test -S "$d/ctrl/wlp1s0";do n=$((n+1));test "$n" -lt 8;sleep 1;done
 ;;
dhcp)
 chmod 700 "$d/dhcp.sh"
 test -x "$d/dhcp.sh"
 /sbin/udhcpc -f -n -q -t 3 -T 2 -i wlp1s0 -s "$d/dhcp.sh" > "$d/dhcp.log" 2>&1
 test -f "$d/bound"
 ;;
restore)
 if test -f "$d/wpa.pid";then
  p=$(cat "$d/wpa.pid");case "$p" in ''|*[!0-9]*)exit 4;;esac
  if test -e "/proc/$p/cmdline";then
   tr '\000' ' ' <"/proc/$p/cmdline" | grep -F "$d/wpa.conf" >/dev/null
   kill "$p"
   n=0;while test -e "/proc/$p";do n=$((n+1));if grep -q "^State:.*Z" "/proc/$p/status";then break;fi;test "$n" -lt 50;sleep 0.1;done
  fi
 fi
 if test -f "$d/started";then
  /sbin/ip addr flush dev wlp1s0
  /usr/bin/wl down
  /usr/bin/wl band "$(cat "$d/band")"
  /usr/bin/wl infra "$(cat "$d/infra")"
  /usr/bin/wl ap "$(cat "$d/ap")"
  if test "$(cat "$d/up")" = 1;then /usr/bin/wl up;fi
 fi
 rm -f "$d/wpa.conf" "$d/wpa.pid" "$d/started" "$d/bound" "$d/dns" "$d/client.sock"
 ;;
*)exit 2;;
esac
