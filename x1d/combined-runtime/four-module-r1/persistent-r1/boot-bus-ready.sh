#!/bin/sh
set -eu
n=0
while :;do
 ready=1
 for name in farm pwrctrl;do
  dbus-send --system --print-reply --reply-timeout=1000 --dest=org.freedesktop.DBus / org.freedesktop.DBus.GetNameOwner string:com.hasselblad.$name >/dev/null 2>&1 || ready=0
 done
 [ "$ready" = 0 ] || exit 0
 n=$((n+1));[ "$n" -lt 20 ] || exit 1
 sleep 1
done
