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
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-early-menu ]
hashok /system/etc/x2d-preview-loader.sh.before-early-menu 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
hashok /system/etc/x2d-preview-loader.sh 0ae12756f9813e0ce62d4e80a462ddbefa706bf239c7a9264be12ab52f939c6f || hashok /system/etc/x2d-preview-loader.sh 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
[ ! -L /system/etc/init/x2d-preview-loader.rc ] && [ ! -L /system/etc/init/x2d-preview-loader.rc.before-early-menu ]
hashok /system/etc/init/x2d-preview-loader.rc.before-early-menu d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
hashok /system/etc/init/x2d-preview-loader.rc 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a || hashok /system/etc/init/x2d-preview-loader.rc d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
trap restore_mount EXIT
( sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
mount -o remount,rw /system
cat /system/etc/x2d-preview-loader.sh.before-early-menu > /system/etc/x2d-preview-loader.sh
chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
cat /system/etc/init/x2d-preview-loader.rc.before-early-menu > /system/etc/init/x2d-preview-loader.rc
chmod 0644 /system/etc/init/x2d-preview-loader.rc
hashok /system/etc/init/x2d-preview-loader.rc d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
sync
restore_mount
[ "$(state)" = "$original" ]
echo EARLY_MENU_ROLLED_BACK
