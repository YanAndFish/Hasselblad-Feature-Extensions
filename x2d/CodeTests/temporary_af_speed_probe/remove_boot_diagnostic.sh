set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
lib=/system/lib64/libx2d_preview_probe.so
rc=/system/etc/init/x2d-preview-probe.rc
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
# Validate all existing targets before deleting either; allow cleanup of a partial install.
if [ -e "$rc" ] || [ -L "$rc" ]; then
    [ ! -L "$rc" ] && hashok "$rc" 7a59dfcf673227347ace4c34665296c1d3059ba5da058f7a9793e78ef47fd0b1 || exit 35
fi
if [ -e "$lib" ] || [ -L "$lib" ]; then
    [ ! -L "$lib" ] && hashok "$lib" 8735037ab1fa050f27e155acf9eee85719d31588e72d82815b824a9e62ba9106 || exit 35
fi
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
trap restore EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 5; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
# Remove the start config first. No stop/restart of any original service.
/system/bin/rm -f "$rc"
/system/bin/rm -f "$lib"
/system/bin/sync
restore
[ ! -e "$rc" ] && [ ! -L "$rc" ] && [ ! -e "$lib" ] && [ ! -L "$lib" ]
[ "$(state)" = "$original" ] || exit 44
echo BOOT_DIAGNOSTIC_REMOVED_RESTORED_RO
