"""离线生成已安装声音候选的原厂链路更新事务；不连接设备。"""
from pathlib import Path
import hashlib, json, wave, array, math

D=Path(__file__).resolve().parent
O=D/'outputs/device-package'
STAGE='/blackbox/x2d-shutter-stage'
OLD_LIB='0a00eb6a034989dc7bf26101dad7c4d8b4d552ecdc03f3b5cec29c3ffad93384'
OLD_WAV='9242fa574231556568c3a1cbde28e9f573b003d655893706343acff423fc6238'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    audio=D/'outputs/ciallo-48k-full.wav'
    with wave.open(str(audio),'rb') as wav:
        assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())==(2,2,48000)
        data=array.array('h',wav.readframes(wav.getnframes()))
    peak=max(abs(n) for n in data)/32768
    files=[('libx2d_audio_preview.so','/system/lib64/libx2d_audio_preview.so',OLD_LIB),
           ('ciallo-48k-full.wav','/system/etc/x2d-ciallo.wav',OLD_WAV)]
    (O/audio.name).write_bytes(audio.read_bytes())
    script='''#!/system/bin/sh
set -eu
export PATH=/system/bin:/system/xbin:/sbin
hashok() { set -- $(sha256sum "$1") "$2"; [ "$1" = "$3" ]; }
[ "$(getprop init.svc.x2d-shutter-audio)" = stopped ]
baseline=$(grep '^/dev/block/mmcblk0p17 /system ext4 ' /proc/mounts)
case "$baseline" in *' ext4 ro,'*) ;; *) exit 31;; esac
hashok /system/etc/x2d-shutter-audio.sh 456ecdba8f772abab7cfcce7e61e7301b3758b708857824cddb49c65ce5f5983
hashok /system/lib64/libaudioclient.so 1a196a3f3c9095042999c429aaf38bcfa2e800f12d4121a6f465cbc4ca18000c
'''
    entries=[]
    for name,target,old in files:
        new=digest(O/name)
        entries.append(dict(source=name,target=target,sha256=new,previous=old))
        script+=f'hashok {target} {old}\nhashok {STAGE}/{name} {new}\n'
        for p in (target,target+'.before-factory-audio',target+'.factory-next'):
            script+=f'[ ! -L {p} ]\n'
        script+=f'[ ! -e {target}.before-factory-audio ]\n[ ! -e {target}.factory-next ]\n'
    script+='success=0; saved=""\nfinish() {\n if [ "$success" != 1 ]; then\n  mount -o remount,rw /system\n'
    # 失败恢复旧文件，但隔离已知有问题的旧播放器，防止下次开机再占用设备。
    script+='  for path in $saved; do cat "$path.before-factory-audio" > "$path.factory-next"; chmod 0644 "$path.factory-next"; mv -f "$path.factory-next" "$path"; done\n'
    script+='  touch /blackbox/x2d-shutter-audio.disable\n  sync\n fi\n mount -o remount,ro /system\n}\ntrap finish EXIT\ntrap "exit 40" HUP INT TERM\nmount -o remount,rw /system\n'
    for e in entries:
        t=e['target'];n=e['source']
        script+=f'(set -C; : > {t}.before-factory-audio)\ncat {t} > {t}.before-factory-audio\nchmod 0644 {t}.before-factory-audio\nhashok {t}.before-factory-audio {e["previous"]}\nsaved="{t} $saved"\n'
        script+=f'cat {STAGE}/{n} > {t}.factory-next\nchmod 0644 {t}.factory-next\nhashok {t}.factory-next {e["sha256"]}\nmv -f {t}.factory-next {t}\n'
    script+='sync\nmount -o remount,ro /system\n[ "$(grep \'^/dev/block/mmcblk0p17 /system ext4 \' /proc/mounts)" = "$baseline" ]\n'
    for e in entries:script+=f'hashok {e["target"]} {e["sha256"]}\n'
    script+='success=1\necho FACTORY_AUDIO_PERSISTED_READONLY\n'
    (O/'install-factory-audio.sh').write_text(script,encoding='utf-8',newline='\n')
    (O/'factory-audio-package.json').write_text(json.dumps(dict(files=entries,peak=peak,peakDbfs=20*math.log10(peak),clippedSamples=sum(n in (-32768,32767) for n in data)),indent=2)+'\n')
    print(f'Offline package ready; peak={peak*100:.3f}%, {20*math.log10(peak):.3f} dBFS')

if __name__=='__main__':main()
