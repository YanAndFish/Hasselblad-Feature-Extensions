"""生成固定路径、哈希约束的安装/卸载请求；不访问相机。"""
import hashlib, json
from pathlib import Path
D=Path(__file__).resolve().parent
files=[
 ('libx2d_preview_loader.so','/system/lib64/libx2d_preview_loader.so'),
 ('boot_preview_loader.sh','/system/etc/x2d-preview-loader.sh'),
 ('resident-code.bin','/system/etc/x2d-preview-code.bin'),
 ('resident-hook.bin','/system/etc/x2d-preview-hook.bin'),
 ('afmf-custom-page.png','/system/etc/x2d-preview-page.png'),
 ('x2d-preview-loader.rc','/system/etc/init/x2d-preview-loader.rc'),
]
entries=[{'source':s,'target':t,'sha256':hashlib.sha256((D/s).read_bytes()).hexdigest()} for s,t in files]
header='''set -eu
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
original=$(state)
case "$original" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) echo BASELINE_MISMATCH; exit 33;; esac
hashok() { actual=$(/system/bin/sha256sum "$1"); [ "${actual%% *}" = "$2" ]; }
restore() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) /system/bin/mount -o remount,ro /system;; esac; }
'''
install=header
for e in entries:
    install+=f'[ ! -e {e["target"]} ] && [ ! -L {e["target"]} ] || exit 34\nhashok /blackbox/x2d-preview-stage/{e["source"]} {e["sha256"]} || exit 35\n'
install+='''made=''
done_ok=0
finish() {
    if [ "$done_ok" = 0 ]; then
        for f in $made; do /system/bin/rm -f "$f"; done
    fi
    restore
}
trap finish EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 10; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
'''
for e in entries:
    t=e['target']
    install+=f'''( set -C; : > {t} )
made="{t} $made"
/system/bin/cat /blackbox/x2d-preview-stage/{e['source']} > {t}
/system/bin/chmod 0644 {t}
hashok {t} {e['sha256']}
'''
install+='''/system/bin/sync
done_ok=1
restore
[ "$(state)" = "$original" ] || exit 44
echo PREVIEW_INSTALLED_RESTORED_RO_NOT_STARTED
'''
remove=header
for e in entries:
    t=e['target']
    remove+=f'if [ -e {t} ] || [ -L {t} ]; then [ ! -L {t} ] && hashok {t} {e["sha256"]} || exit 35; fi\n'
remove+='''trap restore EXIT
trap 'exit 43' HUP INT TERM
( /system/bin/sleep 10; restore ) </dev/null >/dev/null 2>&1 &
/system/bin/mount -o remount,rw /system
'''
for e in reversed(entries): remove+=f'/system/bin/rm -f {e["target"]}\n'
remove+='''/system/bin/sync
restore
[ "$(state)" = "$original" ] || exit 44
echo PREVIEW_FILES_REMOVED_RESTORED_RO
'''
for n,s in [('install_preview_package.sh',install),('remove_preview_package.sh',remove)]:
    (D/n).write_text(s,encoding='ascii',newline='\n')
manifest={'firmware':'first-generation X2D 4.2.0','files':entries,'installHash':hashlib.sha256(install.encode()).hexdigest(),'removeHash':hashlib.sha256(remove.encode()).hexdigest()}
(D/'boot-preview-package.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='ascii')
print('PACKAGE_BUILT_NO_CAMERA_ACCESS')
