#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
[ ! -L /system/etc/init/camera-gui.rc ] && [ ! -L /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu ]
hashok /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu 1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688
hashok /system/etc/init/camera-gui.rc 812034b139f7acaa77a938eaf864489da8725ab7cf2d2ebf7aa8e86cfd0076aa || hashok /system/etc/init/camera-gui.rc 1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688
[ ! -L /system/etc/init/x2d-preview-loader.rc ] && [ ! -L /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu ]
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
hashok /system/etc/init/x2d-preview-loader.rc 5562e4dbbc126dfe723085e8bf20938924431d703ff92cf2b65a217ea0d781cc || hashok /system/etc/init/x2d-preview-loader.rc 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
trap restore_ro EXIT
mount -o remount,rw /system
cat /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu > /system/etc/init/camera-gui.rc
hashok /system/etc/init/camera-gui.rc 1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688
cat /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu > /system/etc/init/x2d-preview-loader.rc
hashok /system/etc/init/x2d-preview-loader.rc 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
sync
restore_ro
[ "$(state)" = "$baseline" ]
echo ORIGINAL_MENU_BOOT_CONFIG_RESTORED
