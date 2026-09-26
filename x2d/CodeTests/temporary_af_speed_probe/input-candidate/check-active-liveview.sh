#!/system/bin/sh
# Bounded menu-lifecycle diagnostic; no focus/shutter/settings operations.
set -u
d=/tmp/x2d-liveview-check
mkdir -m 700 "$d" || exit 31
exec > "$d/result" 2>&1
get() {
 dbus-send --system --print-reply --reply-timeout=1000 --dest=com.hasselblad.camera /camera org.freedesktop.DBus.Properties.Get string:com.hasselblad.camera "string:$1" | awk '/variant[ ]+int32 / {print $NF}'
}
setlv() {
 dbus-send --system --print-reply --reply-timeout=1000 --dest=com.hasselblad.camera /camera com.hasselblad.camera.set_live_view "boolean:$1"
}
owned=0
restore() {
 trap - EXIT HUP INT TERM
 if [ "$owned" = 1 ]; then
  state=$(get live_view_state)
  case "$state" in
   0|4) setlv true; echo "RESTORE_REQUEST=$?";;
   1|2|3) echo ALREADY_RESUMED;;
   *) echo RESTORE_STATE_UNKNOWN;;
  esac
 fi
 sleep 1
 echo "FINAL=$(get live_view_state)"
 echo DONE
}
trap restore EXIT
trap 'exit 43' HUP INT TERM
initial=$(get live_view_state)
echo "INITIAL=$initial"
[ "$initial" = 1 ] || exit 32
exposure=$(get exposure_status)
echo "EXPOSURE=$exposure"
case "$exposure" in 0|512) ;; *) exit 33;; esac
owned=1
setlv false
echo "STOP_REQUEST=$?"
sleep 1
echo "AFTER_STOP=$(get live_view_state)"
