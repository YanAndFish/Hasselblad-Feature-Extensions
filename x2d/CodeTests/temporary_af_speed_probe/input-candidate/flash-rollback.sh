set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
[ ! -L /system/etc/x2d-menu-v1-main.qml ] && [ ! -L /system/etc/x2d-menu-v1-main.qml.before-input-ui ] || exit 34
hashok /system/etc/x2d-menu-v1-main.qml 1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1
hashok /system/etc/x2d-menu-v1-main.qml.before-input-ui f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-input-ui ] || exit 34
hashok /system/etc/x2d-preview-loader.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
hashok /system/etc/x2d-preview-loader.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
[ ! -L /system/etc/x2d-menu-candidate.sh ] && [ ! -L /system/etc/x2d-menu-candidate.sh.before-input-ui ] || exit 34
hashok /system/etc/x2d-menu-candidate.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
hashok /system/etc/x2d-menu-candidate.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
trap restore_mount EXIT
( /system/bin/sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
/system/bin/cat /system/etc/x2d-menu-v1-main.qml.before-input-ui > /system/etc/x2d-menu-v1-main.qml
/system/bin/chmod 0644 /system/etc/x2d-menu-v1-main.qml
hashok /system/etc/x2d-menu-v1-main.qml f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8
/system/bin/cat /system/etc/x2d-preview-loader.sh.before-input-ui > /system/etc/x2d-preview-loader.sh
/system/bin/chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
/system/bin/cat /system/etc/x2d-menu-candidate.sh.before-input-ui > /system/etc/x2d-menu-candidate.sh
/system/bin/chmod 0644 /system/etc/x2d-menu-candidate.sh
hashok /system/etc/x2d-menu-candidate.sh bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
/system/bin/sync
restore_mount
echo PRE_INPUT_MENU_RESTORED
