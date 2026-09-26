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
hashok /system/lib64/libx2d_menu_input.so 5d942911dac34a090347cc8a1c66adcb246c1351b826f6b932b605b17c088729
hashok /system/etc/x2d-preview-native-code.bin 112c43e8e2e331a9673ce1d531ba5a51b2a5796f6214a9c34ae1d58a36224c72
# Runtime readiness and inspect logs are checked by the host through
# the maintenance domain; su does not read private runtime files.
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-early-menu ] && [ ! -L /blackbox/x2d-early-menu-stage/boot_menu_early.sh ]
hashok /blackbox/x2d-early-menu-stage/boot_menu_early.sh 0ae12756f9813e0ce62d4e80a462ddbefa706bf239c7a9264be12ab52f939c6f
hashok /system/etc/x2d-preview-loader.sh 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
[ ! -e /system/etc/x2d-preview-loader.sh.before-early-menu ] || hashok /system/etc/x2d-preview-loader.sh.before-early-menu 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
[ ! -L /system/etc/init/x2d-preview-loader.rc ] && [ ! -L /system/etc/init/x2d-preview-loader.rc.before-early-menu ] && [ ! -L /blackbox/x2d-early-menu-stage/x2d-preview-loader.rc ]
hashok /blackbox/x2d-early-menu-stage/x2d-preview-loader.rc 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
hashok /system/etc/init/x2d-preview-loader.rc d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
[ ! -e /system/etc/init/x2d-preview-loader.rc.before-early-menu ] || hashok /system/etc/init/x2d-preview-loader.rc.before-early-menu d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
done_ok=0; saved=''; created=''
finish() {
 if [ "$done_ok" = 0 ]; then
  for path in $saved; do cat "$path.before-early-menu" > "$path"; chmod 0644 "$path"; done
  for path in $created; do rm -f "$path"; done
  sync
 fi
 restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
mount -o remount,rw /system
if [ ! -e /system/etc/x2d-preview-loader.sh.before-early-menu ]; then (set -C; : > /system/etc/x2d-preview-loader.sh.before-early-menu); cat /system/etc/x2d-preview-loader.sh > /system/etc/x2d-preview-loader.sh.before-early-menu; chmod 0644 /system/etc/x2d-preview-loader.sh.before-early-menu; fi
hashok /system/etc/x2d-preview-loader.sh.before-early-menu 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
saved="/system/etc/x2d-preview-loader.sh $saved"
cat /blackbox/x2d-early-menu-stage/boot_menu_early.sh > /system/etc/x2d-preview-loader.sh
chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh 0ae12756f9813e0ce62d4e80a462ddbefa706bf239c7a9264be12ab52f939c6f
if [ ! -e /system/etc/init/x2d-preview-loader.rc.before-early-menu ]; then (set -C; : > /system/etc/init/x2d-preview-loader.rc.before-early-menu); cat /system/etc/init/x2d-preview-loader.rc > /system/etc/init/x2d-preview-loader.rc.before-early-menu; chmod 0644 /system/etc/init/x2d-preview-loader.rc.before-early-menu; fi
hashok /system/etc/init/x2d-preview-loader.rc.before-early-menu d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
saved="/system/etc/init/x2d-preview-loader.rc $saved"
cat /blackbox/x2d-early-menu-stage/x2d-preview-loader.rc > /system/etc/init/x2d-preview-loader.rc
chmod 0644 /system/etc/init/x2d-preview-loader.rc
hashok /system/etc/init/x2d-preview-loader.rc 8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a
sync
restore_mount
[ "$(state)" = "$original" ]
done_ok=1
echo EARLY_MENU_INSTALLED
