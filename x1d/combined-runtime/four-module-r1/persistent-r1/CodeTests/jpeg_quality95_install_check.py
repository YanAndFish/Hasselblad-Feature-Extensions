"""在工作区副本执行真实 sh 事务，系统挂载/服务使用替身。"""
from pathlib import Path
import sys,os,json,hashlib,subprocess,time
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1]
OUT=P/'build/jpeg-quality95/transaction-tests'/str(time.time_ns())
SHELL='C:/Program Files/Git/bin/sh.exe'
ADDED=['jpeg-daemon-full']
def sha(b):return hashlib.sha256(b).hexdigest()
def posix(p):return '/'+p.drive[0].lower()+p.as_posix()[2:]
def put(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def run(case):
 r=OUT/case;stage=r/'stage';dest=r/'opt/hbl-af-only-v1';bin=r/'bin'
 for p in [stage/'files',dest,bin,r/'etc/systemd/system']:p.mkdir(parents=True)
 put(r/'factory','factory');put(r/'mounts','device / ext4 ro 0 0\n')
 base=(sha(b'factory')+'  '+posix(r/'factory')+'\n').encode()
 old={'baseline.sha256':base,'unchanged-ui':b'original-ui','jpeg-daemon-full':b'old-codec'}
 old['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in old.items()).encode()
 new={**old,**{n:('new '+n).encode() for n in ADDED}}
 del new['manifest.sha256']
 new['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in new.items()).encode()
 for n,b in old.items():(dest/n).write_bytes(b)
 put(dest/'enabled','af-only-v1')
 for n in ['baseline.sha256','manifest.sha256',*ADDED]:(stage/'files'/n).write_bytes(new[n])
 put(stage/'old-pin',sha(old['manifest.sha256']) if case!='wrong-pin' else 'wrong')
 put(stage/'new-pin',sha(new['manifest.sha256']))
 script=(P/'build/jpeg-quality95/stage/repair.sh').read_text().replace('/opt/',posix(r/'opt')+'/').replace('/etc/',posix(r/'etc')+'/').replace('/proc/mounts',posix(r/'mounts'))
 put(stage/'repair.sh',script)
 put(stage/'repair-manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(stage).as_posix()+'\n' for p in stage.rglob('*') if p.is_file()))
 put(bin/'id','#!/bin/sh\necho 0\n');put(bin/'stat','#!/bin/sh\necho 0:700\n')
 put(bin/'sync','#!/bin/sh\nexit 0\n')
 put(bin/'systemctl','#!/bin/sh\necho "$*" >>"$R/events"\ncase "$1" in is-active)exit 0;;show)if [ "$CASE" = override ];then echo DropInPaths=unexpected;else echo DropInPaths=;fi;;*)exit 4;;esac\n')
 put(bin/'mount','#!/bin/sh\necho "mount $*" >>"$R/events"\ncase "$2" in remount,rw)state=rw;;remount,ro)state=ro;;*)exit 4;;esac\necho "device / ext4 $state 0 0" >"$R/mounts"\n')
 put(bin/'mkdir','#!/bin/sh\nif [ "$1" = -m ];then shift 2;fi\nexec /usr/bin/mkdir "$@"\n')
 put(bin/'mv','''#!/bin/sh
case "$CASE:$1" in fail-binary:*/jpeg-daemon-full.batch-next|fail-manifest:*/manifest.sha256.batch-next|fail-enable:*/enabled.batch-next)
 if [ ! -e "$R/fired" ];then touch "$R/fired";exit 4;fi;;esac
exec /usr/bin/mv "$@"
''')
 put(bin/'cp','''#!/bin/sh
case "$CASE:$2" in fail-dropin:*/jpeg-daemon.service.d/93-hbl-full-jpeg.conf)
 if [ ! -e "$R/fired" ];then touch "$R/fired";exit 4;fi;;esac
exec /usr/bin/cp "$@"
''')
 done=subprocess.run([SHELL,'-c','PATH="$1:$PATH";export PATH;exec sh "$2"','check',posix(bin),posix(stage/'repair.sh')],env=dict(os.environ,R=posix(r),CASE=case),capture_output=True,text=True,timeout=30)
 assert ' ext4 ro ' in (r/'mounts').read_text()
 expected=new if case=='normal' else old
 for n,b in expected.items():assert (dest/n).read_bytes()==b,(case,n,done.stdout,done.stderr)
 assert (dest/'enabled').read_text()=='af-only-v1'
 assert (done.returncode==0)==(case=='normal'),(case,done.stdout,done.stderr)
 events=(r/'events').read_text() if (r/'events').exists() else ''
 assert 'restart' not in events and 'daemon-reload' not in events
 if case in ['wrong-pin','override']:assert 'mount' not in events
 return dict(case=case,exit=done.returncode,rootReadOnly=True,rollbackVerified=case!='normal')
cases=[run(c) for c in ['normal','wrong-pin','fail-binary','fail-manifest','fail-enable']]
proof=dict(passed=True,scriptSha256=sha((P/'build/jpeg-quality95/stage/repair.sh').read_bytes()),cases=cases,hardwareRequests=0)
(P/'build/jpeg-quality95/transaction-validation.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof))
