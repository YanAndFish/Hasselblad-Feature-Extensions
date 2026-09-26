#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
hashok /system/lib64/libx2d_native_menu.so b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
hashok /system/etc/X2dNativeMenuBootstrap.qml 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
hashok /system/etc/X2dNativeMenuModel.qml 577e1856c49222e5e22587ab52d021a343b0387305481794ba699b097ab7f56f
hashok /system/etc/X2dNativeMenuRoute.qml 8e96ab55bb9441639f3bd8df7f67892213b568bc31d9c7e4a24558c6f5b01a6f
hashok /system/etc/X2dNativeMenuHost.qml ae9baf71c08018571572bf34e7659025d96fb2551e3aaa8880aa92791331f4cb
hashok /system/etc/X2dFlashIconButton.qml ea8d0b0c8d6b23ce6dcbb0e3279ace0dc078412e62477363ccee8b455c43d163
hashok /system/etc/X2dFlashLampIcon.qml 54dd50efdbd559f595c8acdc4adb1de9ef76e6fddbfbc3f01e0f74ae88d3b6ba
hashok /system/etc/X2dFlashPage.qml b27769af0c04b3b2243bd21ec0a7fdb0206eb72fff5f49ab90d4884645f4d728
hashok /system/etc/X2dFlashStyle.qml 00197fcd000711166e340158c5c86eccf887c1783e743d76af2f90b8ce5455fe
hashok /system/etc/X2dFlashText.qml 5ed7d15aaefef16bf1b0aba834a1e23330cc157ffb6a1598e5bc31f6ca3db281
hashok /system/etc/X2dFlashToggleRow.qml 4a81fc67522d8c338937cefab3bbe8d7d303bc9d2cfaee48b0763385dc12ff9f
hashok /system/etc/X2dFlashValueText.qml 4ac84cac5b7347368df423c1d8557e854c054335b2b3db8dc8b935390921388d
[ ! -L /system/lib64/libx2d_native_menu.so ] && [ ! -e /system/lib64/libx2d_native_menu.so.before-afc ] && [ ! -L /system/lib64/libx2d_native_menu.so.before-afc ]
[ ! -e /system/lib64/libx2d_native_menu.so.x2d-next ] && [ ! -L /system/lib64/libx2d_native_menu.so.x2d-next ]
hashok /blackbox/x2d-original-menu-stage/libx2d_native_menu.so c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
[ ! -L /system/etc/X2dNativeMenuBootstrap.qml ] && [ ! -e /system/etc/X2dNativeMenuBootstrap.qml.before-afc ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.before-afc ]
[ ! -e /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml.x2d-next ]
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
hashok /system/etc/init/camera-gui.rc.before-x2d-native-menu 1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688
[ ! -L /system/etc/init/camera-gui.rc.before-x2d-native-menu ]
[ ! -e /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu ] && [ ! -L /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu ]
hashok /system/etc/init/x2d-preview-loader.rc.before-x2d-native-menu 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
[ ! -L /system/etc/init/x2d-preview-loader.rc.before-x2d-native-menu ]
[ ! -e /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu ] && [ ! -L /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu ]
hashok /system/etc/init/x2d-preview-loader.rc.before-early-menu d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
[ ! -L /system/etc/init/x2d-preview-loader.rc.before-early-menu ]
[ ! -e /system/etc/X2dBackup-x2d-preview-loader.rc.before-early-menu ] && [ ! -L /system/etc/X2dBackup-x2d-preview-loader.rc.before-early-menu ]
hashok /system/etc/init/x2d-preview-loader.rc.before-native-input 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
[ ! -L /system/etc/init/x2d-preview-loader.rc.before-native-input ]
[ ! -e /system/etc/X2dBackup-x2d-preview-loader.rc.before-native-input ] && [ ! -L /system/etc/X2dBackup-x2d-preview-loader.rc.before-native-input ]
hashok /system/etc/init/camera-gui.rc 812034b139f7acaa77a938eaf864489da8725ab7cf2d2ebf7aa8e86cfd0076aa
hashok /system/etc/init/x2d-preview-loader.rc 5562e4dbbc126dfe723085e8bf20938924431d703ff92cf2b65a217ea0d781cc
success=0; saved=''
finish() {
 if [ "$success" != 1 ]; then
   for path in $saved; do
     cat "$path.before-afc" > "$path.x2d-next"
     chmod 0644 "$path.x2d-next"
     mv -f "$path.x2d-next" "$path"
   done
   sync
 fi
 restore_ro
}
trap finish EXIT
trap 'exit 33' HUP INT TERM
mount -o remount,rw /system
cat /system/lib64/libx2d_native_menu.so > /system/lib64/libx2d_native_menu.so.before-afc
chmod 0644 /system/lib64/libx2d_native_menu.so.before-afc
hashok /system/lib64/libx2d_native_menu.so.before-afc b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
saved="/system/lib64/libx2d_native_menu.so $saved"
cat /blackbox/x2d-original-menu-stage/libx2d_native_menu.so > /system/lib64/libx2d_native_menu.so.x2d-next
chmod 0644 /system/lib64/libx2d_native_menu.so.x2d-next
hashok /system/lib64/libx2d_native_menu.so.x2d-next c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
mv -f /system/lib64/libx2d_native_menu.so.x2d-next /system/lib64/libx2d_native_menu.so
hashok /system/lib64/libx2d_native_menu.so c98e73c77da18358537db492bba393864d3c9de0b6a03a1c5dab3fbafba171a5
cat /system/etc/X2dNativeMenuBootstrap.qml > /system/etc/X2dNativeMenuBootstrap.qml.before-afc
chmod 0644 /system/etc/X2dNativeMenuBootstrap.qml.before-afc
hashok /system/etc/X2dNativeMenuBootstrap.qml.before-afc 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
saved="/system/etc/X2dNativeMenuBootstrap.qml $saved"
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml > /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
chmod 0644 /system/etc/X2dNativeMenuBootstrap.qml.x2d-next
hashok /system/etc/X2dNativeMenuBootstrap.qml.x2d-next 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
mv -f /system/etc/X2dNativeMenuBootstrap.qml.x2d-next /system/etc/X2dNativeMenuBootstrap.qml
hashok /system/etc/X2dNativeMenuBootstrap.qml 7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7
mv /system/etc/init/camera-gui.rc.before-x2d-native-menu /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu
hashok /system/etc/X2dBackup-camera-gui.rc.before-x2d-native-menu 1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688
mv /system/etc/init/x2d-preview-loader.rc.before-x2d-native-menu /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-x2d-native-menu 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
mv /system/etc/init/x2d-preview-loader.rc.before-early-menu /system/etc/X2dBackup-x2d-preview-loader.rc.before-early-menu
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-early-menu d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
mv /system/etc/init/x2d-preview-loader.rc.before-native-input /system/etc/X2dBackup-x2d-preview-loader.rc.before-native-input
hashok /system/etc/X2dBackup-x2d-preview-loader.rc.before-native-input 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
sync
restore_ro
[ "$(state)" = "$baseline" ]
success=1
echo ORIGINAL_MENU_AFC_UPDATE_INSTALLED
