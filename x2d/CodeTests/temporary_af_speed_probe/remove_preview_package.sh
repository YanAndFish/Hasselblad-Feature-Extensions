set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
if [ -e /system/lib64/libx2d_preview_loader.so ] || [ -L /system/lib64/libx2d_preview_loader.so ]; then [ ! -L /system/lib64/libx2d_preview_loader.so ] && hashok /system/lib64/libx2d_preview_loader.so 0b8dc35c31dae115535c31efcd2a089f80dd66c75bbe565bf5c2510a86457145 || exit 35; fi
if [ -e /system/etc/x2d-preview-loader.sh ] || [ -L /system/etc/x2d-preview-loader.sh ]; then [ ! -L /system/etc/x2d-preview-loader.sh ] && hashok /system/etc/x2d-preview-loader.sh abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085 || exit 35; fi
if [ -e /system/etc/x2d-preview-code.bin ] || [ -L /system/etc/x2d-preview-code.bin ]; then [ ! -L /system/etc/x2d-preview-code.bin ] && hashok /system/etc/x2d-preview-code.bin e26bf2464af29311790c2e767a3b378a1dd99ad74866711a1ec617272257f8fb || exit 35; fi
if [ -e /system/etc/x2d-preview-hook.bin ] || [ -L /system/etc/x2d-preview-hook.bin ]; then [ ! -L /system/etc/x2d-preview-hook.bin ] && hashok /system/etc/x2d-preview-hook.bin f90186bfe664b507b6f0c867269d877bee06c69dd874960a8d6d08ed29afa202 || exit 35; fi
if [ -e /system/etc/x2d-preview-page.png ] || [ -L /system/etc/x2d-preview-page.png ]; then [ ! -L /system/etc/x2d-preview-page.png ] && hashok /system/etc/x2d-preview-page.png 8d4de634bebc8268f6f24eec8744592600a9175dc3f0afc27499efa4cec0b928 || exit 35; fi
if [ -e /system/etc/init/x2d-preview-loader.rc ] || [ -L /system/etc/init/x2d-preview-loader.rc ]; then [ ! -L /system/etc/init/x2d-preview-loader.rc ] && hashok /system/etc/init/x2d-preview-loader.rc 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67 || exit 35; fi
trap restore EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 10; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
/system/bin/rm -f /system/etc/init/x2d-preview-loader.rc
/system/bin/rm -f /system/etc/x2d-preview-page.png
/system/bin/rm -f /system/etc/x2d-preview-hook.bin
/system/bin/rm -f /system/etc/x2d-preview-code.bin
/system/bin/rm -f /system/etc/x2d-preview-loader.sh
/system/bin/rm -f /system/lib64/libx2d_preview_loader.so
/system/bin/sync
restore
[ "$(state)" = "$original" ] || exit 44
echo PREVIEW_FILES_REMOVED_RESTORED_RO
