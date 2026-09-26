set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
[ ! -e /system/lib64/libx2d_preview_loader.so ] && [ ! -L /system/lib64/libx2d_preview_loader.so ] || exit 34
hashok /blackbox/x2d-preview-stage/libx2d_preview_loader.so 0b8dc35c31dae115535c31efcd2a089f80dd66c75bbe565bf5c2510a86457145 || exit 35
[ ! -e /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh ] || exit 34
hashok /blackbox/x2d-preview-stage/boot_preview_loader.sh abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085 || exit 35
[ ! -e /system/etc/x2d-preview-code.bin ] && [ ! -L /system/etc/x2d-preview-code.bin ] || exit 34
hashok /blackbox/x2d-preview-stage/resident-code.bin e26bf2464af29311790c2e767a3b378a1dd99ad74866711a1ec617272257f8fb || exit 35
[ ! -e /system/etc/x2d-preview-hook.bin ] && [ ! -L /system/etc/x2d-preview-hook.bin ] || exit 34
hashok /blackbox/x2d-preview-stage/resident-hook.bin f90186bfe664b507b6f0c867269d877bee06c69dd874960a8d6d08ed29afa202 || exit 35
[ ! -e /system/etc/x2d-preview-page.png ] && [ ! -L /system/etc/x2d-preview-page.png ] || exit 34
hashok /blackbox/x2d-preview-stage/afmf-custom-page.png 8d4de634bebc8268f6f24eec8744592600a9175dc3f0afc27499efa4cec0b928 || exit 35
[ ! -e /system/etc/init/x2d-preview-loader.rc ] && [ ! -L /system/etc/init/x2d-preview-loader.rc ] || exit 34
hashok /blackbox/x2d-preview-stage/x2d-preview-loader.rc 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67 || exit 35
made=''
done_ok=0
finish() {
    if [ "$done_ok" = 0 ]; then
        for f in $made; do /system/bin/rm -f "$f"; done
    fi
    restore
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 10; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
( set -C; : > /system/lib64/libx2d_preview_loader.so )
made="/system/lib64/libx2d_preview_loader.so $made"
/system/bin/cat /blackbox/x2d-preview-stage/libx2d_preview_loader.so > /system/lib64/libx2d_preview_loader.so
/system/bin/chmod 0644 /system/lib64/libx2d_preview_loader.so
hashok /system/lib64/libx2d_preview_loader.so 0b8dc35c31dae115535c31efcd2a089f80dd66c75bbe565bf5c2510a86457145
( set -C; : > /system/etc/x2d-preview-loader.sh )
made="/system/etc/x2d-preview-loader.sh $made"
/system/bin/cat /blackbox/x2d-preview-stage/boot_preview_loader.sh > /system/etc/x2d-preview-loader.sh
/system/bin/chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085
( set -C; : > /system/etc/x2d-preview-code.bin )
made="/system/etc/x2d-preview-code.bin $made"
/system/bin/cat /blackbox/x2d-preview-stage/resident-code.bin > /system/etc/x2d-preview-code.bin
/system/bin/chmod 0644 /system/etc/x2d-preview-code.bin
hashok /system/etc/x2d-preview-code.bin e26bf2464af29311790c2e767a3b378a1dd99ad74866711a1ec617272257f8fb
( set -C; : > /system/etc/x2d-preview-hook.bin )
made="/system/etc/x2d-preview-hook.bin $made"
/system/bin/cat /blackbox/x2d-preview-stage/resident-hook.bin > /system/etc/x2d-preview-hook.bin
/system/bin/chmod 0644 /system/etc/x2d-preview-hook.bin
hashok /system/etc/x2d-preview-hook.bin f90186bfe664b507b6f0c867269d877bee06c69dd874960a8d6d08ed29afa202
( set -C; : > /system/etc/x2d-preview-page.png )
made="/system/etc/x2d-preview-page.png $made"
/system/bin/cat /blackbox/x2d-preview-stage/afmf-custom-page.png > /system/etc/x2d-preview-page.png
/system/bin/chmod 0644 /system/etc/x2d-preview-page.png
hashok /system/etc/x2d-preview-page.png 8d4de634bebc8268f6f24eec8744592600a9175dc3f0afc27499efa4cec0b928
( set -C; : > /system/etc/init/x2d-preview-loader.rc )
made="/system/etc/init/x2d-preview-loader.rc $made"
/system/bin/cat /blackbox/x2d-preview-stage/x2d-preview-loader.rc > /system/etc/init/x2d-preview-loader.rc
/system/bin/chmod 0644 /system/etc/init/x2d-preview-loader.rc
hashok /system/etc/init/x2d-preview-loader.rc 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
/system/bin/sync
done_ok=1
restore
[ "$(state)" = "$original" ] || exit 44
echo PREVIEW_INSTALLED_RESTORED_RO_NOT_STARTED
