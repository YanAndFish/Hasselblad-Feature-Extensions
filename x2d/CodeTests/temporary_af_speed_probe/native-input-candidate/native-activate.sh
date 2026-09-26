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
[ ! -L /system/etc/x2d-preview-loader.sh ] && [ ! -L /system/etc/x2d-preview-loader.sh.before-native-input ] && [ ! -L /blackbox/x2d-native-stage/boot_menu_native.sh ]
hashok /blackbox/x2d-native-stage/boot_menu_native.sh 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
hashok /system/etc/x2d-preview-loader.sh 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
[ ! -e /system/etc/x2d-preview-loader.sh.before-native-input ] || hashok /system/etc/x2d-preview-loader.sh.before-native-input 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
[ ! -L /system/etc/init/x2d-preview-loader.rc ] && [ ! -L /system/etc/init/x2d-preview-loader.rc.before-native-input ] && [ ! -L /blackbox/x2d-native-stage/x2d-preview-loader.rc.candidate ]
hashok /blackbox/x2d-native-stage/x2d-preview-loader.rc.candidate d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
hashok /system/etc/init/x2d-preview-loader.rc 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
[ ! -e /system/etc/init/x2d-preview-loader.rc.before-native-input ] || hashok /system/etc/init/x2d-preview-loader.rc.before-native-input 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
done_ok=0; saved=''; created=''
finish() {
 if [ "$done_ok" = 0 ]; then
  for path in $saved; do cat "$path.before-native-input" > "$path"; chmod 0644 "$path"; done
  for path in $created; do rm -f "$path"; done
  sync
 fi
 restore_mount
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &
mount -o remount,rw /system
if [ ! -e /system/etc/x2d-preview-loader.sh.before-native-input ]; then (set -C; : > /system/etc/x2d-preview-loader.sh.before-native-input); cat /system/etc/x2d-preview-loader.sh > /system/etc/x2d-preview-loader.sh.before-native-input; chmod 0644 /system/etc/x2d-preview-loader.sh.before-native-input; fi
hashok /system/etc/x2d-preview-loader.sh.before-native-input 059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721
saved="/system/etc/x2d-preview-loader.sh $saved"
cat /blackbox/x2d-native-stage/boot_menu_native.sh > /system/etc/x2d-preview-loader.sh
chmod 0644 /system/etc/x2d-preview-loader.sh
hashok /system/etc/x2d-preview-loader.sh 46f18db298629b37f97e15bb6b70af8097b01c86b3fd981bf98dbdc917d36ccb
if [ ! -e /system/etc/init/x2d-preview-loader.rc.before-native-input ]; then (set -C; : > /system/etc/init/x2d-preview-loader.rc.before-native-input); cat /system/etc/init/x2d-preview-loader.rc > /system/etc/init/x2d-preview-loader.rc.before-native-input; chmod 0644 /system/etc/init/x2d-preview-loader.rc.before-native-input; fi
hashok /system/etc/init/x2d-preview-loader.rc.before-native-input 8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67
saved="/system/etc/init/x2d-preview-loader.rc $saved"
cat /blackbox/x2d-native-stage/x2d-preview-loader.rc.candidate > /system/etc/init/x2d-preview-loader.rc
chmod 0644 /system/etc/init/x2d-preview-loader.rc
hashok /system/etc/init/x2d-preview-loader.rc d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc
sync
restore_mount
[ "$(state)" = "$original" ]
done_ok=1
echo NATIVE_ACTIVATE_OK
