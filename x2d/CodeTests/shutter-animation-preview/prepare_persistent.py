"""生成默认启用的启动配置及精确恢复事务；本脚本不访问设备。"""
from pathlib import Path
import hashlib, json

D=Path(__file__).resolve().parent
O=D/'outputs/device-package'
STAGE='/blackbox/x2d-shutter-stage'
OLD='cded1a09b5de14f73a8b9efcfa8f041dc40afd7c777f666f628cfe32e22245ae'
BOOT='c27cc4e408152db67ab2f98d37841ec344176f2335894d9c72866bc15bcd9c27'
ORIGINAL='7bd57701e10d6ffb4d04164fb9718c5d1b92f8cb6143aa1b4be5b2ed171709d7'


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    O.mkdir(parents=True,exist_ok=True)
    launcher='''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
# 常驻服务同时承接已有标记的三状态读写；禁用效果不能退出设置服务。
# 无标记默认两者开启；旧空标记=仅动画；0/1 内容分别为关/仅动画。
# 一次冷启动对照：先消费标记，再退出；后续开机仍按默认配置启动。
if [ -e /blackbox/x2d-shutter-audio.skip-once ]; then
    rm /blackbox/x2d-shutter-audio.skip-once
    echo AUDIO_SKIPPED_ONCE > /tmp/x2d-shutter-audio.log
    exit 0
fi
echo $$ > /tmp/x2d-shutter-audio.pid
export X2D_AUDIO_SERVICE=1
export LD_PRELOAD=/system/lib64/libx2d_audio_preview.so
exec /system/bin/sleep 2147483647 > /tmp/x2d-shutter-audio.log 2>&1
'''
    rc='''# X2D 100C 4.2.0 独立声音候选；不替换 camera-gui 或原厂音频服务。
service x2d-shutter-audio /system/bin/sh /system/etc/x2d-shutter-audio.sh
    class core
    user root
    group root
    seclabel u:r:shell:s0
    oneshot

# 非 critical，失败不会引发重启循环或阻止拍摄界面启动。
'''
    (O/'x2d-shutter-audio.sh').write_text(launcher,encoding='utf-8',newline='\n')
    (O/'x2d-shutter-audio.rc').write_text(rc,encoding='utf-8',newline='\n')
    (O/'X2dShutterAnimation.qml').write_bytes((D/'X2dShutterAnimation.qml').read_bytes())
    (O/'x2d-ciallo.wav').write_bytes((D/'outputs/ciallo-48k-full.wav').read_bytes())
    targets={
        'libx2d_audio_preview.so':'/system/lib64/libx2d_audio_preview.so',
        'x2d-ciallo.wav':'/system/etc/x2d-ciallo.wav',
        'x2d-shutter-audio.sh':'/system/etc/x2d-shutter-audio.sh',
        'x2d-shutter-audio.rc':'/system/etc/init/x2d-shutter-audio.rc',
        'X2dShutterAnimation.qml':'/system/etc/X2dShutterAnimation.qml',
    }
    entries=[dict(source=n,target=t,sha256=sha((O/n).read_bytes())) for n,t in targets.items()]
    qml=targets['X2dShutterAnimation.qml'];backup=qml+'.before-persistent'
    header='''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
state() { grep '^/dev/block/mmcblk0p17 /system ext4 ' /proc/mounts; }
baseline=$(state)
case "$baseline" in *' ext4 ro,'*) ;; *) exit 31;; esac
'''
    s=header+f'hashok {qml} {OLD}\nhashok /system/etc/X2dNativeMenuBootstrap.qml {BOOT}\n'
    s+=f'[ ! -e {backup} ] && [ ! -L {backup} ]\n'
    for e in entries:
        t=e['target'];s+=f'hashok {STAGE}/{e["source"]} {e["sha256"]}\n[ ! -L {t} ]\n'
        if t!=qml:s+=f'[ ! -e {t} ]\n'
        s+=f'[ ! -e {t}.shutter-next ] && [ ! -L {t}.shutter-next ]\n'
    s+='success=0; saved=0; created=""\n'
    s+=f'''finish() {{
 if [ "$success" != 1 ]; then
  mount -o remount,rw /system
  if [ "$saved" = 1 ]; then cat {backup} > {qml}.shutter-next; chmod 0644 {qml}.shutter-next; mv -f {qml}.shutter-next {qml}; fi
  for path in $created; do rm -f "$path" "$path.shutter-next"; done
  sync
 fi
 mount -o remount,ro /system
}}
trap finish EXIT
trap 'exit 40' HUP INT TERM
mount -o remount,rw /system
(set -C; : > {backup})
cat {qml} > {backup}
chmod 0644 {backup}
hashok {backup} {OLD}
saved=1
'''
    for e in entries:
        t=e['target']
        if t!=qml:s+=f'created="{t} $created"\n'
        s+=f'cat {STAGE}/{e["source"]} > {t}.shutter-next\nchmod 0644 {t}.shutter-next\nhashok {t}.shutter-next {e["sha256"]}\nmv -f {t}.shutter-next {t}\n'
    s+='sync\nmount -o remount,ro /system\n[ "$(state)" = "$baseline" ]\n'
    for e in entries:s+=f'hashok {e["target"]} {e["sha256"]}\n'
    s+='success=1\necho SHUTTER_PERSISTENT_INSTALLED_READONLY\n'
    (O/'install-persistent.sh').write_text(s,encoding='utf-8',newline='\n')
    # 完整撤回新增效果，保留原菜单扩展；调用前须停止声音并在完成后重载 GUI。
    restore=header+f'hashok /system/etc/X2dNativeMenuBootstrap.qml {BOOT}\nhashok /system/etc/X2dNativeMenuBootstrap.qml.before-shutter {ORIGINAL}\n'
    for e in entries:restore+=f'hashok {e["target"]} {e["sha256"]}\n'
    restore+='trap "mount -o remount,ro /system" EXIT\nmount -o remount,rw /system\n'
    restore+='cat /system/etc/X2dNativeMenuBootstrap.qml.before-shutter > /system/etc/X2dNativeMenuBootstrap.qml.shutter-next\nchmod 0644 /system/etc/X2dNativeMenuBootstrap.qml.shutter-next\n'
    restore+=f'hashok /system/etc/X2dNativeMenuBootstrap.qml.shutter-next {ORIGINAL}\nmv -f /system/etc/X2dNativeMenuBootstrap.qml.shutter-next /system/etc/X2dNativeMenuBootstrap.qml\n'
    for e in entries:restore+=f'rm {e["target"]}\n'
    restore+='sync\nmount -o remount,ro /system\n[ "$(state)" = "$baseline" ]\necho SHUTTER_PERSISTENT_REMOVED_READONLY\n'
    (O/'restore-persistent.sh').write_text(restore,encoding='utf-8',newline='\n')
    (O/'persistent-package.json').write_text(json.dumps(dict(model='X2D 100C',firmware='4.2.0',files=entries,defaultEnabled=True,coldBootVerified=False),indent=2)+'\n')
    print('Prepared persistent default-on package and rollback; no device access.')


if __name__=='__main__':main()
