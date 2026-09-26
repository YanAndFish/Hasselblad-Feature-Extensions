#!/system/bin/sh
# Read-only costs, not end-to-end button or display latency.
set -eu
export PATH=/system/bin:/system/xbin:/sbin
. /tmp/x2d-preview/state
[ "$(awk '{print $22}' /proc/$page_pid/stat)" = "$page_start" ] || exit 31
stamp() { read now unused < /proc/uptime; }
report() { stamp; awk -v name="$1" -v before="$before" -v after="$now" 'BEGIN {printf "%s %.0f ms\n",name,(after-before)*1000}'; }
i=0
while [ "$i" -lt 3 ]; do
 stamp; before=$now
 awk '{print $22}' /proc/$page_pid/stat >/dev/null
 report process_identity
 stamp; before=$now
 dd if=/proc/$page_pid/mem bs=1 skip="$visible_address" count=1 2>/dev/null | od -An -tu1 | tr -d ' \n' >/dev/null
 report visibility_read
 stamp; before=$now
 dbus-send --system --print-reply --reply-timeout=1000 --dest=com.hasselblad.camera /camera org.freedesktop.DBus.Properties.Get string:com.hasselblad.camera string:live_view_state >/dev/null
 report liveview_query
 stamp; before=$now
 dbus-send --system --print-reply --reply-timeout=1000 --dest=com.hasselblad.camera /camera org.freedesktop.DBus.Properties.Get string:com.hasselblad.camera string:exposure_status >/dev/null
 report exposure_query
 i=$((i+1))
done
