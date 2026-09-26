"""生成仅安装扩展文件的事务；不修改原厂 GUI 或启动配置。"""
import hashlib
import json
from pathlib import Path
import tarfile

D=Path(__file__).resolve().parent
O=D/'native-package'
manifest=json.loads((O/'package.json').read_text())
stage='/blackbox/x2d-original-menu-stage'
shell='''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
[ "$(id -u)" = 0 ] && [ "$(cat /proc/self/attr/current)" = u:r:su:s0 ] || exit 31
state() { while read -r dev path fs options rest; do [ "$path" != /system ] || printf '%s %s %s\\n' "$dev" "$fs" "$options"; done < /proc/mounts; }
baseline=$(state)
case "$baseline" in '/dev/block/mmcblk0p17 ext4 ro,'*) ;; *) exit 32;; esac
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
'''
for f in manifest['files']:
    assert '..' not in f['source'] and not f['source'].startswith('/')
    assert f['target'].startswith(('/system/etc/X2d','/system/lib64/libx2d_native_menu.so'))
    shell+=f'[ ! -e {f["target"]} ] && [ ! -L {f["target"]} ] || exit 33\n'
    shell+=f'hashok {stage}/{f["source"]} {f["sha256"]}\n'
shell+='''success=0
restore_ro() { case "$(state)" in '/dev/block/mmcblk0p17 ext4 rw,'*) mount -o remount,ro /system;; esac; }
finish() {
 if [ "$success" != 1 ]; then
'''
for f in manifest['files']: shell+=f'  rm -f {f["target"]}\n'
shell+=''' fi
 restore_ro
}
trap finish EXIT
trap 'exit 34' HUP INT TERM
mount -o remount,rw /system
'''
for f in manifest['files']:
    shell+=f'cat {stage}/{f["source"]} > {f["target"]}\nchmod 0644 {f["target"]}\nhashok {f["target"]} {f["sha256"]}\n'
shell+='sync\nrestore_ro\n[ "$(state)" = "$baseline" ]\nsuccess=1\necho ORIGINAL_MENU_FILES_INSTALLED\n'
(O/'install-files.sh').write_text(shell,encoding='ascii',newline='\n')
with tarfile.open(O/'files.tar.gz','w:gz') as archive:
    for name in [f['source'] for f in manifest['files']]+['install-files.sh']:
        archive.add(O/name,arcname=name,recursive=False)
print(json.dumps(dict(files=len(manifest['files']),archiveBytes=(O/'files.tar.gz').stat().st_size,
                     installerSha256=hashlib.sha256((O/'install-files.sh').read_bytes()).hexdigest())))
