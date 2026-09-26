set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
[ ! -L /system/etc/x2d-menu-v1-main.qml ] && [ ! -L /system/etc/x2d-menu-v1-main.qml.before-flash-ui ] || exit 34
hashok /system/etc/x2d-menu-v1-main.qml f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8
hashok /system/etc/x2d-menu-v1-main.qml.before-flash-ui 39ef3ee7b2e65db1776c769c03dc36333ced31c3e822ace90128a9ea901c7a0d
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-flash-ui ] || exit 34
hashok /system/etc/x2d-preview-loader.sh bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
hashok /system/etc/x2d-preview-loader.sh.before-flash-ui f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
[ ! -L /system/etc/x2d-menu-candidate.sh ] && [ ! -L /system/etc/x2d-menu-candidate.sh.before-flash-ui ] || exit 34
hashok /system/etc/x2d-menu-candidate.sh bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
hashok /system/etc/x2d-menu-candidate.sh.before-flash-ui f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
trap restore_mount EXIT
( /system/bin/sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
/system/bin/cat /system/etc/x2d-menu-v1-main.qml.before-flash-ui > /system/etc/x2d-menu-v1-main.qml
/system/bin/chmod 0644 /system/etc/x2d-menu-v1-main.qml
hashok /system/etc/x2d-menu-v1-main.qml 39ef3ee7b2e65db1776c769c03dc36333ced31c3e822ace90128a9ea901c7a0d
/system/bin/cat /system/etc/x2d-preview-loader.sh.before-flash-ui > /system/etc/x2d-preview-loader.sh
/system/bin/chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
/system/bin/cat /system/etc/x2d-menu-candidate.sh.before-flash-ui > /system/etc/x2d-menu-candidate.sh
/system/bin/chmod 0644 /system/etc/x2d-menu-candidate.sh
hashok /system/etc/x2d-menu-candidate.sh f4bae13c6a95881f374a24a143e5d8e5d05e0c217f1a7c1da28fdaa50af28c68
/system/bin/sync
restore_mount
echo PRE_FLASH_MENU_RESTORED
