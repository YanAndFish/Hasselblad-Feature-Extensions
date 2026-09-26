#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
# Original executable hashes are checked through the existing maintenance
# domain by Deploy-NativeMenu.ps1; su cannot read those labeled executables.
[ ! -L /system/lib64/libx2d_menu_input.so ] && [ ! -L /system/lib64/libx2d_menu_input.so.before-native-input ] && [ ! -L /blackbox/x2d-native-stage/libx2d_menu_input.so ]
hashok /blackbox/x2d-native-stage/libx2d_menu_input.so 5d942911dac34a090347cc8a1c66adcb246c1351b826f6b932b605b17c088729
[ ! -e /system/lib64/libx2d_menu_input.so ]
[ ! -L /system/etc/x2d-preview-native-code.bin ] && [ ! -L /system/etc/x2d-preview-native-code.bin.before-native-input ] && [ ! -L /blackbox/x2d-native-stage/resident-code.bin ]
hashok /blackbox/x2d-native-stage/resident-code.bin 112c43e8e2e331a9673ce1d531ba5a51b2a5796f6214a9c34ae1d58a36224c72
[ ! -e /system/etc/x2d-preview-native-code.bin ]
done_ok=0; saved=''; created=''
finish() {
 if [ "$done_ok" = 0 ]; then
  for path in $saved; do cat "$path.before-native-input" > "$path"; chmod 0644 "$path"; done
  for path in $created; do rm -f "$path"; done
  sync
 fi
 restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
mount -o remount,rw /system
created="/system/lib64/libx2d_menu_input.so $created"
(set -C; : > /system/lib64/libx2d_menu_input.so)
cat /blackbox/x2d-native-stage/libx2d_menu_input.so > /system/lib64/libx2d_menu_input.so
chmod 0644 /system/lib64/libx2d_menu_input.so
hashok /system/lib64/libx2d_menu_input.so 5d942911dac34a090347cc8a1c66adcb246c1351b826f6b932b605b17c088729
created="/system/etc/x2d-preview-native-code.bin $created"
(set -C; : > /system/etc/x2d-preview-native-code.bin)
cat /blackbox/x2d-native-stage/resident-code.bin > /system/etc/x2d-preview-native-code.bin
chmod 0644 /system/etc/x2d-preview-native-code.bin
hashok /system/etc/x2d-preview-native-code.bin 112c43e8e2e331a9673ce1d531ba5a51b2a5796f6214a9c34ae1d58a36224c72
sync
restore_mount
[ "$(state)" = "$original" ]
done_ok=1
echo NATIVE_PREPARE_OK
