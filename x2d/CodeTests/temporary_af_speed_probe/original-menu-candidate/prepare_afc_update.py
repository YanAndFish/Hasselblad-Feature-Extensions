"""更新已安装菜单的两个文件；原子替换库，备份移出 init 扫描目录。只生成。"""
import hashlib
import json
import tarfile
from pathlib import Path
D=Path(__file__).resolve().parent
O=D/'native-package'
before=json.loads((O/'package.before-afc.json').read_text())
after=json.loads((O/'package.json').read_text())
old={f['target']:f for f in before['files']}
changes=[dict(f,before=old[f['target']]['sha256']) for f in after['files'] if f['sha256']!=old[f['target']]['sha256']]
assert {f['source'] for f in changes}=={'libx2d_native_menu.so','X2dNativeMenuBootstrap.qml'}
migrations=[
 ('camera-gui.rc.before-x2d-native-menu','1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688'),
 ('x2d-preview-loader.rc.before-x2d-native-menu','8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a'),
 ('x2d-preview-loader.rc.before-early-menu','d18d2ef4353f5a0a795ce940b0161c4bccdaf66ff04192c0055afad086b98cdc'),
 ('x2d-preview-loader.rc.before-native-input','8461e0a18f4fa564612c1388dda88c4c24273e82ac2a0c550ab1e43d68570d67')]
stage='/blackbox/x2d-original-menu-stage'
head='''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
'''
s=head
for f in before['files']:s+=f'hashok {f["target"]} {f["sha256"]}\n'
for f in changes:
    t=f['target']
    s+=f'[ ! -L {t} ] && [ ! -e {t}.before-afc ] && [ ! -L {t}.before-afc ]\n'
    s+=f'[ ! -e {t}.x2d-next ] && [ ! -L {t}.x2d-next ]\nhashok {stage}/{f["source"]} {f["sha256"]}\n'
for name,digest in migrations:
    s+=f'hashok /system/etc/init/{name} {digest}\n[ ! -L /system/etc/init/{name} ]\n'
    s+=f'[ ! -e /system/etc/X2dBackup-{name} ] && [ ! -L /system/etc/X2dBackup-{name} ]\n'
for e in json.loads((O/'boot-transaction.json').read_text())['entries']:
    s+=f'hashok {e["target"]} {e["after"]}\n'
s+='''success=0; saved=''
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
'''
for f in changes:
    t=f['target']
    s+=f'cat {t} > {t}.before-afc\nchmod 0644 {t}.before-afc\nhashok {t}.before-afc {f["before"]}\n'
    s+=f'saved="{t} $saved"\ncat {stage}/{f["source"]} > {t}.x2d-next\nchmod 0644 {t}.x2d-next\n'
    s+=f'hashok {t}.x2d-next {f["sha256"]}\nmv -f {t}.x2d-next {t}\nhashok {t} {f["sha256"]}\n'
for name,digest in migrations:
    s+=f'mv /system/etc/init/{name} /system/etc/X2dBackup-{name}\nhashok /system/etc/X2dBackup-{name} {digest}\n'
s+='sync\nrestore_ro\n[ "$(state)" = "$baseline" ]\nsuccess=1\necho ORIGINAL_MENU_AFC_UPDATE_INSTALLED\n'
(O/'update-afc.sh').write_text(s,encoding='ascii',newline='\n')
s=head
for f in changes:
    t=f['target']
    s+=f'[ ! -L {t} ] && [ ! -L {t}.before-afc ] && [ ! -e {t}.x2d-next ] && [ ! -L {t}.x2d-next ]\n'
    s+=f'hashok {t} {f["sha256"]}\nhashok {t}.before-afc {f["before"]}\n'
s+='''stopped=0
finish() { sync; restore_ro; if [ "$stopped" = 1 ]; then start camera-gui; fi; }
trap finish EXIT
trap 'exit 40' HUP INT TERM
[ "$(getprop init.svc.camera-gui)" = running ]
set -- $(pidof camera-gui)
[ "$#" = 1 ]
stopped=1
stop camera-gui
i=0
while pidof camera-gui >/dev/null 2>&1 && [ "$i" -lt 100 ]; do sleep .1; i=$((i+1)); done
if pidof camera-gui >/dev/null 2>&1; then exit 41; fi
mount -o remount,rw /system
'''
for f in changes:
    t=f['target']
    s+=f'cat {t}.before-afc > {t}.x2d-next\nchmod 0644 {t}.x2d-next\nhashok {t}.x2d-next {f["before"]}\nmv -f {t}.x2d-next {t}\n'
s+='sync\nrestore_ro\n[ "$(state)" = "$baseline" ]\nstart camera-gui\nstopped=0\necho ORIGINAL_MENU_AFC_UPDATE_RESTORED\n'
(O/'restore-afc.sh').write_text(s,encoding='ascii',newline='\n')
with tarfile.open(O/'afc-update.tar.gz','w:gz') as archive:
    for name in [f['source'] for f in changes]+['update-afc.sh','restore-afc.sh','restore-boot.sh']:
        archive.add(O/name,arcname=name,recursive=False)
(D/'afc-update-manifest.json').write_text(json.dumps(dict(changes=changes,backupMigrations=migrations,
     deployed=False,guiRestarted=False),indent=2)+'\n')
print(json.dumps(dict(changedFiles=len(changes),archiveBytes=(O/'afc-update.tar.gz').stat().st_size,
                     installerSha256=hashlib.sha256((O/'update-afc.sh').read_bytes()).hexdigest())))
