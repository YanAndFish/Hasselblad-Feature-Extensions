"""生成开机激活和撤回配置；不会连接相机或执行安装。"""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
from inspect_menu_resources import load_gui
from firmware_image import system_file
O=D/'native-package'
raw=system_file('/etc/init/camera-gui.rc')
assert hashlib.sha256(raw).hexdigest()=='1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688'
old_preview=(D.parent/'native-early-boot-candidate/x2d-preview-loader.rc').read_bytes()
assert hashlib.sha256(old_preview).hexdigest()=='8d3772f07571f50b734ea62a5e70ae75f71d17947d1fa5bbba6fd974cd30233a'
first=b'service camera-gui /system/bin/camera-gui -platform wayland-egl --fullscreen\n'
assert raw.count(first)==1
new=raw.replace(first,first+b'    setenv X2D_NATIVE_MENU 1\n    setenv LD_PRELOAD /system/lib64/libx2d_native_menu.so\n',1)
assert new.count(b'service ')==raw.count(b'service ')
old_trigger=b'on post-fs\n    start x2d-preview-loader\n\n'
assert old_preview.count(old_trigger)==1
preview=old_preview.replace(old_trigger,b'# Independent preview retained for manual rollback, not auto-started.\n',1)
entries=[]
for source,target,before,after in [
    ('camera-gui.rc.native','/system/etc/init/camera-gui.rc',raw,new),
    ('x2d-preview-loader.rc.manual','/system/etc/init/x2d-preview-loader.rc',old_preview,preview)]:
    (O/source).write_bytes(after)
    entries.append(dict(source=source,target=target,before=hashlib.sha256(before).hexdigest(),after=hashlib.sha256(after).hexdigest()))
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
stage='/blackbox/x2d-original-menu-stage'
def backup_for(target):
    # 启动目录可能解析非 .rc 后缀文件；备份必须放到目录外。
    return '/system/etc/X2dBackup-'+Path(target).name+'.before-x2d-native-menu'
s=head
for e in entries:
    t=e['target'];backup=backup_for(t)
    s+=f'[ ! -L {t} ] && [ ! -L {backup} ]\nhashok {t} {e["before"]}\n'
    s+=f'[ ! -e {backup} ] || hashok {backup} {e["before"]}\n'
    s+=f'hashok {stage}/{e["source"]} {e["after"]}\n'
for f in json.loads((O/'package.json').read_text())['files']:
    s+=f'hashok {f["target"]} {f["sha256"]}\n'
s+='''success=0; saved=''
finish() {
 if [ "$success" != 1 ]; then
   for path in $saved; do
     name=${path##*/}
     cat "/system/etc/X2dBackup-$name.before-x2d-native-menu" > "$path"
   done
   sync
 fi
 restore_ro
}
trap finish EXIT
trap 'exit 33' HUP INT TERM
mount -o remount,rw /system
'''
for e in entries:
    t=e['target'];backup=backup_for(t)
    s+=f'if [ ! -e {backup} ]; then (set -C; : > {backup}); cat {t} > {backup}; chmod 0644 {backup}; fi\nhashok {backup} {e["before"]}\n'
    s+=f'saved="{t} $saved"\ncat {stage}/{e["source"]} > {t}\nhashok {t} {e["after"]}\n'
s+='sync\nrestore_ro\n[ "$(state)" = "$baseline" ]\nsuccess=1\necho ORIGINAL_MENU_BOOT_CONFIG_INSTALLED\n'
(O/'activate-boot.sh').write_text(s,encoding='ascii',newline='\n')
s=head
for e in entries:
    t=e['target'];backup=backup_for(t)
    s+=f'[ ! -L {t} ] && [ ! -L {backup} ]\nhashok {backup} {e["before"]}\nhashok {t} {e["after"]} || hashok {t} {e["before"]}\n'
s+='trap restore_ro EXIT\nmount -o remount,rw /system\n'
for e in entries:
    s+=f'cat {backup_for(e["target"])} > {e["target"]}\nhashok {e["target"]} {e["before"]}\n'
s+='sync\nrestore_ro\n[ "$(state)" = "$baseline" ]\necho ORIGINAL_MENU_BOOT_CONFIG_RESTORED\n'
(O/'restore-boot.sh').write_text(s,encoding='ascii',newline='\n')
(O/'boot-transaction.json').write_text(json.dumps(dict(entries=entries,deployed=False,
    activationRequires='temporary original menu attachment and interaction verified'),indent=2)+'\n')
print('Prepared two guarded boot configuration changes and rollback; not executed')
