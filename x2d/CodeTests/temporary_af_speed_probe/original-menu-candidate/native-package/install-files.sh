#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
[ ! -e /system/lib64/libx2d_native_menu.so ] && [ ! -L /system/lib64/libx2d_native_menu.so ] || exit 33
hashok /blackbox/x2d-original-menu-stage/libx2d_native_menu.so b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
[ ! -e /system/etc/X2dNativeMenuBootstrap.qml ] && [ ! -L /system/etc/X2dNativeMenuBootstrap.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
[ ! -e /system/etc/X2dNativeMenuModel.qml ] && [ ! -L /system/etc/X2dNativeMenuModel.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuModel.qml 577e1856c49222e5e22587ab52d021a343b0387305481794ba699b097ab7f56f
[ ! -e /system/etc/X2dNativeMenuRoute.qml ] && [ ! -L /system/etc/X2dNativeMenuRoute.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuRoute.qml 8e96ab55bb9441639f3bd8df7f67892213b568bc31d9c7e4a24558c6f5b01a6f
[ ! -e /system/etc/X2dNativeMenuHost.qml ] && [ ! -L /system/etc/X2dNativeMenuHost.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dNativeMenuHost.qml ae9baf71c08018571572bf34e7659025d96fb2551e3aaa8880aa92791331f4cb
[ ! -e /system/etc/X2dFlashIconButton.qml ] && [ ! -L /system/etc/X2dFlashIconButton.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashIconButton.qml ea8d0b0c8d6b23ce6dcbb0e3279ace0dc078412e62477363ccee8b455c43d163
[ ! -e /system/etc/X2dFlashLampIcon.qml ] && [ ! -L /system/etc/X2dFlashLampIcon.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashLampIcon.qml 54dd50efdbd559f595c8acdc4adb1de9ef76e6fddbfbc3f01e0f74ae88d3b6ba
[ ! -e /system/etc/X2dFlashPage.qml ] && [ ! -L /system/etc/X2dFlashPage.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashPage.qml b27769af0c04b3b2243bd21ec0a7fdb0206eb72fff5f49ab90d4884645f4d728
[ ! -e /system/etc/X2dFlashStyle.qml ] && [ ! -L /system/etc/X2dFlashStyle.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashStyle.qml 00197fcd000711166e340158c5c86eccf887c1783e743d76af2f90b8ce5455fe
[ ! -e /system/etc/X2dFlashText.qml ] && [ ! -L /system/etc/X2dFlashText.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashText.qml 5ed7d15aaefef16bf1b0aba834a1e23330cc157ffb6a1598e5bc31f6ca3db281
[ ! -e /system/etc/X2dFlashToggleRow.qml ] && [ ! -L /system/etc/X2dFlashToggleRow.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashToggleRow.qml 4a81fc67522d8c338937cefab3bbe8d7d303bc9d2cfaee48b0763385dc12ff9f
[ ! -e /system/etc/X2dFlashValueText.qml ] && [ ! -L /system/etc/X2dFlashValueText.qml ] || exit 33
hashok /blackbox/x2d-original-menu-stage/X2dFlashValueText.qml 4ac84cac5b7347368df423c1d8557e854c054335b2b3db8dc8b935390921388d
success=0
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
finish() {
 if [ "$success" != 1 ]; then
  rm -f /system/lib64/libx2d_native_menu.so
  rm -f /system/etc/X2dNativeMenuBootstrap.qml
  rm -f /system/etc/X2dNativeMenuModel.qml
  rm -f /system/etc/X2dNativeMenuRoute.qml
  rm -f /system/etc/X2dNativeMenuHost.qml
  rm -f /system/etc/X2dFlashIconButton.qml
  rm -f /system/etc/X2dFlashLampIcon.qml
  rm -f /system/etc/X2dFlashPage.qml
  rm -f /system/etc/X2dFlashStyle.qml
  rm -f /system/etc/X2dFlashText.qml
  rm -f /system/etc/X2dFlashToggleRow.qml
  rm -f /system/etc/X2dFlashValueText.qml
 fi
 restore_ro
}
trap finish EXIT
trap 'exit 34' HUP INT TERM
mount -o remount,rw /system
cat /blackbox/x2d-original-menu-stage/libx2d_native_menu.so > /system/lib64/libx2d_native_menu.so
chmod 0644 /system/lib64/libx2d_native_menu.so
hashok /system/lib64/libx2d_native_menu.so b96cd5856c8637f06070f90458e4d873d82645a6fc707bfe301d20d45aaaa11c
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuBootstrap.qml > /system/etc/X2dNativeMenuBootstrap.qml
chmod 0644 /system/etc/X2dNativeMenuBootstrap.qml
hashok /system/etc/X2dNativeMenuBootstrap.qml 3da63065d76b37275af8456363eb89e9479b422f825e2bf591b75f2ca25d3d84
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuModel.qml > /system/etc/X2dNativeMenuModel.qml
chmod 0644 /system/etc/X2dNativeMenuModel.qml
hashok /system/etc/X2dNativeMenuModel.qml 577e1856c49222e5e22587ab52d021a343b0387305481794ba699b097ab7f56f
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuRoute.qml > /system/etc/X2dNativeMenuRoute.qml
chmod 0644 /system/etc/X2dNativeMenuRoute.qml
hashok /system/etc/X2dNativeMenuRoute.qml 8e96ab55bb9441639f3bd8df7f67892213b568bc31d9c7e4a24558c6f5b01a6f
cat /blackbox/x2d-original-menu-stage/X2dNativeMenuHost.qml > /system/etc/X2dNativeMenuHost.qml
chmod 0644 /system/etc/X2dNativeMenuHost.qml
hashok /system/etc/X2dNativeMenuHost.qml ae9baf71c08018571572bf34e7659025d96fb2551e3aaa8880aa92791331f4cb
cat /blackbox/x2d-original-menu-stage/X2dFlashIconButton.qml > /system/etc/X2dFlashIconButton.qml
chmod 0644 /system/etc/X2dFlashIconButton.qml
hashok /system/etc/X2dFlashIconButton.qml ea8d0b0c8d6b23ce6dcbb0e3279ace0dc078412e62477363ccee8b455c43d163
cat /blackbox/x2d-original-menu-stage/X2dFlashLampIcon.qml > /system/etc/X2dFlashLampIcon.qml
chmod 0644 /system/etc/X2dFlashLampIcon.qml
hashok /system/etc/X2dFlashLampIcon.qml 54dd50efdbd559f595c8acdc4adb1de9ef76e6fddbfbc3f01e0f74ae88d3b6ba
cat /blackbox/x2d-original-menu-stage/X2dFlashPage.qml > /system/etc/X2dFlashPage.qml
chmod 0644 /system/etc/X2dFlashPage.qml
hashok /system/etc/X2dFlashPage.qml b27769af0c04b3b2243bd21ec0a7fdb0206eb72fff5f49ab90d4884645f4d728
cat /blackbox/x2d-original-menu-stage/X2dFlashStyle.qml > /system/etc/X2dFlashStyle.qml
chmod 0644 /system/etc/X2dFlashStyle.qml
hashok /system/etc/X2dFlashStyle.qml 00197fcd000711166e340158c5c86eccf887c1783e743d76af2f90b8ce5455fe
cat /blackbox/x2d-original-menu-stage/X2dFlashText.qml > /system/etc/X2dFlashText.qml
chmod 0644 /system/etc/X2dFlashText.qml
hashok /system/etc/X2dFlashText.qml 5ed7d15aaefef16bf1b0aba834a1e23330cc157ffb6a1598e5bc31f6ca3db281
cat /blackbox/x2d-original-menu-stage/X2dFlashToggleRow.qml > /system/etc/X2dFlashToggleRow.qml
chmod 0644 /system/etc/X2dFlashToggleRow.qml
hashok /system/etc/X2dFlashToggleRow.qml 4a81fc67522d8c338937cefab3bbe8d7d303bc9d2cfaee48b0763385dc12ff9f
cat /blackbox/x2d-original-menu-stage/X2dFlashValueText.qml > /system/etc/X2dFlashValueText.qml
chmod 0644 /system/etc/X2dFlashValueText.qml
hashok /system/etc/X2dFlashValueText.qml 4ac84cac5b7347368df423c1d8557e854c054335b2b3db8dc8b935390921388d
sync
restore_ro
[ "$(state)" = "$baseline" ]
success=1
echo ORIGINAL_MENU_FILES_INSTALLED
