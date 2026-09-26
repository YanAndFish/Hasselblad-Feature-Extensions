#!/bin/sh
set -eu
d=/run/hbl-hotspot-test
test "$interface" = wlp1s0
case "$1" in
bound|renew)
  /sbin/ifconfig "$interface" "$ip" netmask "$subnet" up
  for r in $router;do /sbin/route add default gw "$r" dev "$interface";break;done
  umask 077
  printf '%s\n' "$dns" >"$d/dns"
  printf ready >"$d/bound"
  ;;
esac
