#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
# Original executable hashes are checked through the existing maintenance
# domain by Deploy-NativeMenu.ps1; su cannot read those labeled executables.
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-native-input ]
hashok /system/etc/x2d-preview-loader.sh.before-native-input 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
hashok /system/etc/x2d-preview-loader.sh 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb || hashok /system/etc/x2d-preview-loader.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
[ ! -L /system/etc/init/x2d-preview-loader.rc ] && [ ! -L /system/etc/init/x2d-preview-loader.rc.before-native-input ]
hashok /system/etc/init/x2d-preview-loader.rc.before-native-input 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
hashok /system/etc/init/x2d-preview-loader.rc d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc || hashok /system/etc/init/x2d-preview-loader.rc 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
trap restore_mount EXIT
( sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
mount -o remount,rw /system
cat /system/etc/x2d-preview-loader.sh.before-native-input > /system/etc/x2d-preview-loader.sh
chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
cat /system/etc/init/x2d-preview-loader.rc.before-native-input > /system/etc/init/x2d-preview-loader.rc
chmod 0644 /system/etc/init/x2d-preview-loader.rc
hashok /system/etc/init/x2d-preview-loader.rc 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
sync
restore_mount
[ "$(state)" = "$original" ]
echo NATIVE_ROLLBACK_OK
