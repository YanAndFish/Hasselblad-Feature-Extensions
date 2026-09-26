set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
# The normal maintenance domain verifies the original GUI before staging.
# This su-domain transaction only touches our system_file additions.
hashok /system/etc/x2d-preview-loader.sh abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085
if [ -e /system/lib64/libx2d_menu_gate.so ]; then [ ! -L /system/lib64/libx2d_menu_gate.so ] && hashok /system/lib64/libx2d_menu_gate.so b1d2f86e8a650187d370ff964bd6afcda2227b7ca3aff87dbc890d5a7aaf844b || exit 35; fi
if [ -e /system/etc/x2d-menu-v1-main.qml ]; then [ ! -L /system/etc/x2d-menu-v1-main.qml ] && hashok /system/etc/x2d-menu-v1-main.qml 39ef3ee7b2e65db1776c769c03dc36333ced31c3e822ace90128a9ea901c7a0d || exit 35; fi
if [ -e /system/etc/x2d-menu-candidate.sh ]; then [ ! -L /system/etc/x2d-menu-candidate.sh ] && hashok /system/etc/x2d-menu-candidate.sh ee88ba07aeb7711a2af505a7bba6381468a9dbb8a9e96bf52e594257761b9f12 || exit 35; fi
trap restore EXIT
/system/bin/mount -o remount,rw /system
/system/bin/rm -f /system/lib64/libx2d_menu_gate.so
/system/bin/rm -f /system/etc/x2d-menu-v1-main.qml
/system/bin/rm -f /system/etc/x2d-menu-candidate.sh
/system/bin/sync
restore
echo MENU_CANDIDATE_FILES_REMOVED
