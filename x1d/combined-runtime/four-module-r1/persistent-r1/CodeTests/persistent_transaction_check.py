"""在私有目录运行真实 sh 文件事务；mount/systemd/基线设备均为替身。"""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;WORK=HERE.parent;ROOT=WORK.parents[3]
OUT=HERE/'pt'/str(time.time_ns())
SHELL=Path('C:/Program Files/Git/bin/sh.exe')
source=(WORK/'install.sh').read_text(encoding='utf-8')
def sha(b):return hashlib.sha256(b).hexdigest()
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def run(case):
    root=OUT/case;stage=root/'stage';bin=root/'bin'
    for p in (stage,bin,root/'opt',root/'etc',root/'lib'):p.mkdir(parents=True,exist_ok=True)
    package=WORK/'build/persistent-package'
    files={n:(package/n).read_bytes() for _,n in (line.split() for line in (package/'manifest.sha256').read_text().splitlines())}
    text=source.replace('/etc/systemd/system',posix(root/'etc')).replace('/lib/systemd/system',posix(root/'lib')).replace('/opt',posix(root/'opt')).replace('/proc/mounts',posix(root/'mounts'))
    files['install.sh']=text.encode()
    files['baseline.sha256']=(sha(b'factory')+'  '+posix(root/'factory')+'\n').encode()
    put(root/'factory','factory' if case!='bad-baseline' else 'changed')
    for n,b in files.items():p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    manifest=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    (stage/'manifest.sha256').write_bytes(manifest)
    put(root/'mounts','device / ext4 ro 0 0\n')
    put(bin/'id','#!/bin/sh\nprintf 0\n')
    put(bin/'stat','#!/bin/sh\nprintf 0:700\n')
    # Windows ACL 无法代表设备 Unix mode；权限检查由 stat 替身承担。
    put(bin/'mkdir','#!/bin/sh\nif [ "$1" = -m ];then shift 2;fi\nexec /usr/bin/mkdir "$@"\n')
    put(bin/'df','#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted\\n/dev/root 50000 1000 49000 2%% /\\n"\n')
    put(bin/'sync','#!/bin/sh\nexit 0\n')
    put(bin/'mount','''#!/bin/sh
printf 'mount %s\n' "$*" >>"$TEST_ROOT/events"
case "$2" in remount,rw) state=rw;;remount,ro)state=ro;;*)exit 3;;esac
printf 'device / ext4 %s 0 0\n' "$state" >"$TEST_ROOT/mounts"
''')
    put(bin/'systemctl','#!/bin/sh\nprintf "systemctl %s\\n" "$*" >>"$TEST_ROOT/events"\n[ "$1" = is-active ]\n')
    put(bin/'cp','''#!/bin/sh
printf 'cp %s\n' "$*" >>"$TEST_ROOT/events"
case "$CASE:$2" in fail-farm-drop:*/92-hbl-four-module.conf.new) case "$1" in */farm.conf)exit 4;;esac;;esac
case "$CASE:$1" in fail-payload:*/runtime/libhbl-formal.so)exit 4;;esac
exec /usr/bin/cp "$@"
''')
    put(bin/'mv','''#!/bin/sh
printf 'mv %s\n' "$*" >>"$TEST_ROOT/events"
case "$CASE:$1" in fail-enable:*/enabled.next)exit 4;;esac
exec /usr/bin/mv "$@"
''')
    if case=='existing-package':put(root/'opt/hbl-four-module-v1/other','keep')
    env=dict(os.environ,CASE=case,TEST_ROOT=posix(root))
    done=subprocess.run([str(SHELL),'-c','PATH="$1:$PATH";export PATH;exec sh "$2" install "$3"','check',posix(bin),posix(stage/'install.sh'),sha(manifest)],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    events=(root/'events').read_text(encoding='utf-8') if (root/'events').exists() else ''
    assert 'restart' not in events and 'daemon-reload' not in events
    assert ' ext4 ro ' in (root/'mounts').read_text()
    dest=root/'opt/hbl-four-module-v1'
    gui=root/'etc/victory-gui.service.d/92-hbl-four-module.conf'
    farm=root/'etc/msg2dbus-farm.service.d/92-hbl-four-module.conf'
    if case=='normal':
        assert done.returncode==0,(done.stdout,done.stderr)
        assert (dest/'enabled').read_text().strip()=='enabled-current-firmware' and gui.is_file() and farm.is_file()
        assert events.rindex('/farm.conf')<events.index('/enabled.next')
    else:
        assert done.returncode!=0,(case,done.stdout)
        assert not gui.exists() and not farm.exists(),(case,done.stdout,done.stderr)
        if case=='existing-package':assert (dest/'other').read_text()=='keep'
        else:assert not dest.exists() and not (root/'opt/hbl-four-module-v1.installing').exists(),(case,done.stdout,done.stderr)
        if case in ('bad-baseline','existing-package'):assert 'mount ' not in events
    return {'case':case,'exit':done.returncode,'result':done.stdout.strip()}

def main():
    for n in ('install.sh','boot-common.sh','boot-farm.sh','boot-gui.sh','boot-coordinate.sh'):
        subprocess.run([str(SHELL),'-n',str(WORK/n)],check=True)
    results=[run(c) for c in ('normal','bad-baseline','existing-package','fail-payload','fail-farm-drop','fail-enable')]
    proof={'passed':True,'hardwareRequests':0,'scriptSha256':sha((WORK/'install.sh').read_bytes()),'cases':results}
    (HERE/'persistent-transaction-validation.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(proof))
if __name__=='__main__':main()
