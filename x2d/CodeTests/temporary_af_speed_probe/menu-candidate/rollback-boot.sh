set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
boot=/system/etc/x2d-preview-loader.sh
candidate=/system/etc/x2d-menu-candidate.sh
backup=/system/etc/x2d-preview-loader.previous.sh
[ ! -L "$boot" ] && [ ! -L "$candidate" ] && [ ! -L "$backup" ] || exit 34
hashok "$boot" f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
hashok "$backup" abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085
trap restore_mount EXIT
( /system/bin/sleep 15; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
/system/bin/cat "$backup" > "$boot"
/system/bin/chmod 0644 "$boot"
hashok "$boot" abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085
/system/bin/sync
restore_mount
echo ORIGINAL_PREVIEW_BOOT_RESTORED
