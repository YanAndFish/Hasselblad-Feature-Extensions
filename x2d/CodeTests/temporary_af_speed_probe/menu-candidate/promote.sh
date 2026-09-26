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
hashok "$boot" abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085
hashok "$candidate" ee88ba07aeb7711a2af505a7bba6381468a9dbb8a9e96bf52e594257761b9f12
hashok /blackbox/x2d-menu-stage/boot_menu_fixed.sh f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
hashok /system/lib64/libx2d_menu_gate.so b1d2f86e8a650187d370ff964bd6afcda2227b7ca3aff87dbc890d5a7aaf844b
hashok /system/etc/x2d-menu-v1-main.qml 39ef3ee7b2e65db1776c769c03dc36333ced31c3e822ace90128a9ea901c7a0d
[ ! -e "$backup" ] || exit 35
done_ok=0; backup_ready=0
finish() {
  if [ "$done_ok" = 0 ] && [ "$backup_ready" = 1 ]; then
    /system/bin/cat "$backup" > "$boot"
    /system/bin/chmod 0644 "$boot"
    /system/bin/sync
  fi
  restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 15; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
(set -C; : > "$backup")
/system/bin/cat "$boot" > "$backup"
/system/bin/chmod 0644 "$backup"
hashok "$backup" abbce7a604008fe331ccc8d1ba872528022df4e1a70be226745c3736560e1085
backup_ready=1
/system/bin/cat /blackbox/x2d-menu-stage/boot_menu_fixed.sh > "$candidate"
hashok "$candidate" f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
/system/bin/cat /blackbox/x2d-menu-stage/boot_menu_fixed.sh > "$boot"
/system/bin/chmod 0644 "$boot" "$candidate"
hashok "$boot" f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
/system/bin/sync
restore_mount
[ "$(state)" = "$original" ] || exit 44
done_ok=1
echo HIDDEN_MENU_BOOT_INSTALLED
