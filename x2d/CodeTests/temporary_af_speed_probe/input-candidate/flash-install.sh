set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
[ ! -L /system/etc/x2d-menu-v1-main.qml ] && [ ! -L /system/etc/x2d-menu-v1-main.qml.before-input-ui ] || exit 34
if [ -e /system/etc/x2d-menu-v1-main.qml.before-input-ui ]; then hashok /system/etc/x2d-menu-v1-main.qml.before-input-ui f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8; fi
hashok /system/etc/x2d-menu-v1-main.qml.before-input-ui f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8
hashok /system/etc/x2d-menu-v1-main.qml 1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1
hashok /blackbox/x2d-input-stage/flash-x2d-menu-v1-main.qml 1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-input-ui ] || exit 34
if [ -e /system/etc/x2d-preview-loader.sh.before-input-ui ]; then hashok /system/etc/x2d-preview-loader.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457; fi
hashok /system/etc/x2d-preview-loader.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
hashok /system/etc/x2d-preview-loader.sh fcab807960bafee6d05fd0425a37ea4d5a0e13d40775b1460802852b3408376d
hashok /blackbox/x2d-input-stage/flash-boot_menu_candidate.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
[ ! -L /system/etc/x2d-menu-candidate.sh ] && [ ! -L /system/etc/x2d-menu-candidate.sh.before-input-ui ] || exit 34
if [ -e /system/etc/x2d-menu-candidate.sh.before-input-ui ]; then hashok /system/etc/x2d-menu-candidate.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457; fi
hashok /system/etc/x2d-menu-candidate.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
hashok /system/etc/x2d-menu-candidate.sh fcab807960bafee6d05fd0425a37ea4d5a0e13d40775b1460802852b3408376d
hashok /blackbox/x2d-input-stage/flash-boot_menu_candidate.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
done_ok=0; saved=''
finish() {
 if [ "$done_ok" = 0 ]; then
  for path in $saved; do /system/bin/cat "$path.before-input-ui" > "$path"; /system/bin/chmod 0644 "$path"; done
  /system/bin/sync
 fi
 restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
if [ ! -e /system/etc/x2d-menu-v1-main.qml.before-input-ui ]; then
(set -C; : > /system/etc/x2d-menu-v1-main.qml.before-input-ui)
/system/bin/cat /system/etc/x2d-menu-v1-main.qml > /system/etc/x2d-menu-v1-main.qml.before-input-ui
/system/bin/chmod 0644 /system/etc/x2d-menu-v1-main.qml.before-input-ui
fi
hashok /system/etc/x2d-menu-v1-main.qml.before-input-ui f7305289e6d92e77288bca2e9f08e7b85fa7333eea4580976de0aad3c51c9ff8
saved="/system/etc/x2d-menu-v1-main.qml $saved"
if [ ! -e /system/etc/x2d-preview-loader.sh.before-input-ui ]; then
(set -C; : > /system/etc/x2d-preview-loader.sh.before-input-ui)
/system/bin/cat /system/etc/x2d-preview-loader.sh > /system/etc/x2d-preview-loader.sh.before-input-ui
/system/bin/chmod 0644 /system/etc/x2d-preview-loader.sh.before-input-ui
fi
hashok /system/etc/x2d-preview-loader.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
saved="/system/etc/x2d-preview-loader.sh $saved"
if [ ! -e /system/etc/x2d-menu-candidate.sh.before-input-ui ]; then
(set -C; : > /system/etc/x2d-menu-candidate.sh.before-input-ui)
/system/bin/cat /system/etc/x2d-menu-candidate.sh > /system/etc/x2d-menu-candidate.sh.before-input-ui
/system/bin/chmod 0644 /system/etc/x2d-menu-candidate.sh.before-input-ui
fi
hashok /system/etc/x2d-menu-candidate.sh.before-input-ui bce48a50b40ed61a5be08f20bd3744f65956b22e16ee70e865b5248dc966d457
saved="/system/etc/x2d-menu-candidate.sh $saved"
/system/bin/cat /blackbox/x2d-input-stage/flash-x2d-menu-v1-main.qml > /system/etc/x2d-menu-v1-main.qml
/system/bin/chmod 0644 /system/etc/x2d-menu-v1-main.qml
hashok /system/etc/x2d-menu-v1-main.qml 1d6ed58559c3ef3f2c8015121b0fb5ecb4aa1854e6eb003cdb5d81f6f41695b1
/system/bin/cat /blackbox/x2d-input-stage/flash-boot_menu_candidate.sh > /system/etc/x2d-preview-loader.sh
/system/bin/chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
/system/bin/cat /blackbox/x2d-input-stage/flash-boot_menu_candidate.sh > /system/etc/x2d-menu-candidate.sh
/system/bin/chmod 0644 /system/etc/x2d-menu-candidate.sh
hashok /system/etc/x2d-menu-candidate.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
/system/bin/sync
restore_mount
[ "$(state)" = "$original" ] || exit 44
done_ok=1
echo INPUT_UI_INSTALLED
