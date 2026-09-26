"""生成版本绑定的原生菜单安装事务；本脚本不连接相机。"""
import hashlib
import json
from pathlib import Path
import subprocess

D = Path(__file__).resolve().parent
O = D / 'native-input-candidate'
stage = '/blackbox/x2d-native-stage'
manifest = json.loads((O/'package.json').read_text())
items = manifest['files']
old = {
    '/system/etc/x2d-preview-loader.sh': '059d191c6e1dc54a6f5cdf5135e64159a7dfd011ce24b52c3967885bdafe9721',
    '/system/etc/init/x2d-preview-loader.rc': '8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67',
}
header = '''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 33;; esac
hashok() { actual=$(sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore_mount() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
# Original executable hashes are checked through the existing maintenance
# domain by Deploy-NativeMenu.ps1; su cannot read those labeled executables.
'''

for phase, selected in [('prepare',items[:2]), ('activate',items[2:])]:
    s=header
    if phase=='activate':
        for f in items[:2]:
            s+=f'hashok {f["target"]} {f["sha256"]}\n'
        s+='# Runtime readiness and inspect logs are checked by the host through\n# the maintenance domain; su does not read private runtime files.\n'
    for f in selected:
        t=f['target']; backup=t+'.before-native-input'
        s+=f'[ ! -L {t} ] && [ ! -L {backup} ] && [ ! -L {stage}/{f["source"]} ]\n'
        s+=f'hashok {stage}/{f["source"]} {f["sha256"]}\n'
        if t in old:
            s+=f'hashok {t} {old[t]}\n[ ! -e {backup} ] || hashok {backup} {old[t]}\n'
        else:
            s+=f'[ ! -e {t} ]\n'
    s+='''done_ok=0; saved=''; created=''
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
'''
    for f in selected:
        t=f['target']; backup=t+'.before-native-input'
        if t in old:
            s+=f'if [ ! -e {backup} ]; then (set -C; : > {backup}); cat {t} > {backup}; chmod 0644 {backup}; fi\nhashok {backup} {old[t]}\n'
            s+=f'saved="{t} $saved"\n'
        else:
            s+=f'created="{t} $created"\n(set -C; : > {t})\n'
        s+=f'cat {stage}/{f["source"]} > {t}\nchmod 0644 {t}\nhashok {t} {f["sha256"]}\n'
    s+=f'sync\nrestore_mount\n[ "$(state)" = "$original" ]\ndone_ok=1\necho NATIVE_{phase.upper()}_OK\n'
    (O/f'native-{phase}.sh').write_text(s,encoding='ascii',newline='\n')

# Rollback restores only our two owned configuration files. Candidate modules
# remain inert until they can be removed after all owned users have exited.
s=header
for f in items[2:]:
    t=f['target']; backup=t+'.before-native-input'
    s+=f'[ ! -L {t} ] && [ ! -L {backup} ]\nhashok {backup} {old[t]}\n'
    s+=f'hashok {t} {f["sha256"]} || hashok {t} {old[t]}\n'
s+='trap restore_mount EXIT\n( sleep 20; restore_mount ) </dev/null >/dev/null 2>&1 &\nmount -o remount,rw /system\n'
for t,h in old.items():
    s+=f'cat {t}.before-native-input > {t}\nchmod 0644 {t}\nhashok {t} {h}\n'
s+='sync\nrestore_mount\n[ "$(state)" = "$original" ]\necho NATIVE_ROLLBACK_OK\n'
(O/'native-rollback.sh').write_text(s,encoding='ascii',newline='\n')

# Reuse reviewed read-only address decoding from the stable loader, with no
# preview creation, input opening, mapping mutation, or process cleanup.
base=(D/'input-candidate/boot_menu_candidate.sh').read_text()
helpers=base[base.index('add() {'):base.index('samegui() {')]
decode=base[base.index('rw() {'):base.index("input=''; count=0")]
s='''#!/system/bin/sh
set -eu
d=/tmp/x2d-preview
[ "$(cat "$d/status")" = READY ]
[ ! -e "$d/native-state" ] && [ ! -e "$d/native-inspect.log" ]
fail() { echo "$1"; exit 20; }
'''+helpers+'''
for key in gui_pid gui_start page_pid page_start mailbox visible_address; do
 value=$(sed -n "s/^$key=//p" "$d/state")
 case "$value" in ''|*[!0-9]*) exit 40;; esac
 eval "$key=$value"
done
[ "$(startof "$gui_pid")" = "$gui_start" ] && [ "$(startof "$page_pid")" = "$page_start" ]
basehex=$(awk '$2=="r-xp" && $3=="00000000" && $NF=="/system/bin/camera-gui" {split($1,v,"-");print v[1]}' "$d/gui.maps")
case "$basehex" in ''|*[!0-9a-f]*) exit 41;; esac
base=$(hexnum "$basehex")
'''+decode+'''
[ "$original_function" = 0 ] || fail FRONT_NOT_OWNED
(set -C; : > "$d/native-state")
printf 'gui_pid=%s\\ngui_start=%s\\npage_pid=%s\\npage_start=%s\\nmailbox=%s\\nvisible_address=%s\\nmap_pointer_address=%s\\nmap_pointer=%s\\nkey_address=%s\\nmodifiers_address=%s\\nfunction_address=%s\\n' "$gui_pid" "$gui_start" "$page_pid" "$page_start" "$mailbox" "$visible_address" "$map_pointer_address" "$map_pointer" "$key_address" "$modifiers_address" "$function_address" > "$d/native-state"
X2D_MENU_INPUT_MODE=inspect LD_PRELOAD=/system/lib64/libx2d_menu_input.so /system/bin/camera-test --version
cat "$d/native-inspect.log"
'''
(O/'native-inspect.sh').write_text(s,encoding='ascii',newline='\n')
for name in ('native-prepare.sh','native-activate.sh','native-rollback.sh','native-inspect.sh'):
    subprocess.run(['C:/Program Files/Git/bin/bash.exe','-n',str(O/name)],check=True)
(O/'transaction.json').write_text(json.dumps({'baseline':old,'files':{n:hashlib.sha256((O/n).read_bytes()).hexdigest() for n in ('native-prepare.sh','native-activate.sh','native-rollback.sh','native-inspect.sh')},'executed':False},indent=2)+'\n')
print('NATIVE_TRANSACTION_BUILT_OFFLINE')
