"""固定文件修复事务的真实 sh 故障注入；没有设备操作。"""
from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;WORK=HERE.parent;OUT=HERE/'hub-fix-repair'/str(time.time_ns())
SHELL='C:/Program Files/Git/bin/sh.exe'
FILES=['libhbl-af-loader.so','common.sh','farm.sh','manifest.sha256']
def sha(b):return hashlib.sha256(b).hexdigest()
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def run(case):
    root=OUT/case;stage=root/'stage';dest=root/'opt/hbl-af-only-v1';bin=root/'bin'
    for p in (stage,dest,bin):p.mkdir(parents=True,exist_ok=True)
    put(root/'factory','factory');put(root/'mounts','device / ext4 ro 0 0\n')
    base=sha(b'factory')+'  '+posix(root/'factory')+'\n'
    def package(version):
        data={n:version.encode() for n in FILES if n not in ('manifest.sha256','installed.manifest.sha256')};data['baseline.sha256']=base.encode()
        data['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(data.items())).encode()
        data['installed.manifest.sha256']=(sha(data['manifest.sha256'])+'\n').encode()
        return data
    old=package('old');new=package('new')
    for n,b in old.items():p=dest/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    put(dest/'enabled','af-only-v1\n')
    for n in FILES:p=stage/'files'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(new[n])
    put(stage/'old-pin',sha(old['manifest.sha256']) if case!='wrong-old' else 'wrong')
    put(stage/'new-pin',sha(new['manifest.sha256']))
    text=(WORK/'repair-af-hub-fix.sh').read_text(encoding='utf-8').replace('/opt',posix(root/'opt')).replace('/proc/mounts',posix(root/'mounts'))
    put(stage/'repair-batch.sh',text)
    members=[p for p in stage.rglob('*') if p.is_file()]
    put(stage/'repair-manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(stage).as_posix()+'\n' for p in members))
    put(bin/'id','#!/bin/sh\necho 0\n');put(bin/'stat','#!/bin/sh\necho 0:700\n')
    put(bin/'mkdir','#!/bin/sh\nif [ "$1" = -m ];then shift 2;fi\nexec /usr/bin/mkdir "$@"\n')
    put(bin/'sync','#!/bin/sh\nexit 0\n')
    put(bin/'systemctl','#!/bin/sh\necho "$*" >>"$R/events"\n[ "$1" = is-active ]\n')
    put(bin/'mount','''#!/bin/sh
echo "mount $*" >>"$R/events"
case "$2" in remount,rw)state=rw;;remount,ro)state=ro;;*)exit 1;;esac
echo "device / ext4 $state 0 0" >"$R/mounts"
''')
    put(bin/'mv','''#!/bin/sh
echo "mv $*" >>"$R/events"
case "$CASE:$1" in
fail-file:*/libhbl-af-loader.so.batch-next|fail-manifest:*/manifest.sha256.batch-next|fail-enable:*/enabled.batch-next)
 if [ ! -f "$R/fired" ];then touch "$R/fired";exit 4;fi;;esac
exec /usr/bin/mv "$@"
''')
    original_inode=(dest/'libhbl-af-loader.so').stat().st_ino
    done=subprocess.run([SHELL,'-c','PATH="$1:$PATH";export PATH;exec sh "$2"','check',posix(bin),posix(stage/'repair-batch.sh')],env=dict(os.environ,R=posix(root),CASE=case),capture_output=True,text=True,timeout=30)
    assert ' ext4 ro ' in (root/'mounts').read_text()
    if case!='wrong-old':
        backup=dest/'.hub-fix-backup/libhbl-af-loader.so'
        assert backup.stat().st_ino==original_inode and backup.read_bytes()==old['libhbl-af-loader.so']
    expected=new if case=='normal' else old
    for n in FILES:assert (dest/n).read_bytes()==expected[n],(case,n,done.stderr)
    assert (dest/'enabled').read_text()=='af-only-v1\n'
    events=(root/'events').read_text() if (root/'events').exists() else ''
    assert 'restart' not in events and 'daemon-reload' not in events
    if case=='normal':assert done.returncode==0,(done.stdout,done.stderr)
    else:assert done.returncode!=0
    if case=='wrong-old':assert 'mount' not in events
    return {'case':case,'exit':done.returncode,'rootReadOnly':True,'filesVerified':True}
results=[run(c) for c in ('normal','wrong-old','fail-file','fail-manifest','fail-enable')]
proof={'passed':True,'hardwareRequests':0,'scriptSha256':sha((WORK/'repair-af-hub-fix.sh').read_bytes()),'cases':results}
(HERE/'hub-fix-repair-validation.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof))
