set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
lib=/system/lib64/libx2d_preview_probe.so
rc=/system/etc/init/x2d-preview-probe.rc
stage=/blackbox/x2d-autoload-probe
lh=8735037ab1fa050f27e155acf9eee85719d31588e72d82815b824a9e62ba9106
rh=7a59dfcf673227347ace4c34665296c1d3059ba5da058f7a9793e78ef47fd0b1
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
[ ! -e "$lib" ] && [ ! -L "$lib" ] && [ ! -e "$rc" ] && [ ! -L "$rc" ] || exit 34
hashok "$stage/libx2d_preview_probe.so" "$lh" || exit 35
hashok "$stage/x2d-preview-probe.rc" "$rh" || exit 35
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
done_ok=0
made_lib=0
made_rc=0
finish() {
    if [ "$done_ok" = 0 ]; then
        [ "$made_rc" = 0 ] || /system/bin/rm -f "$rc"
        [ "$made_lib" = 0 ] || /system/bin/rm -f "$lib"
    fi
    restore
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 5; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
( set -C; : > "$lib" )
made_lib=1
/system/bin/cat "$stage/libx2d_preview_probe.so" > "$lib"
/system/bin/chmod 0644 "$lib"
hashok "$lib" "$lh"
# Install the config last; partial library placement never enables a boot service.
( set -C; : > "$rc" )
made_rc=1
/system/bin/cat "$stage/x2d-preview-probe.rc" > "$rc"
/system/bin/chmod 0644 "$rc"
hashok "$rc" "$rh"
/system/bin/sync
done_ok=1
restore
[ "$(state)" = "$original" ] || exit 44
echo BOOT_DIAGNOSTIC_INSTALLED_NOT_STARTED
/system/bin/ls -lZ "$lib" "$rc"
echo RESTORED_EXACT
