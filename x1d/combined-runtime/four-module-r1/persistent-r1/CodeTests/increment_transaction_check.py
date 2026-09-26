"""在隔离文件目录模拟成对升级、拒绝与回退，不访问真实设备。"""
from pathlib import Path
import hashlib,json,os,shlex,subprocess,sys,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;WORK=HERE.parent
OUT=HERE/'increment-transaction-output'/str(time.time_ns())
SHELL='C:/Program Files/Git/bin/sh.exe'
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(data if isinstance(data,bytes) else data.encode('utf-8'))
FAKE=r'''from pathlib import Path
import os,sys,json
r=Path(os.environ['CAL_TEST_ROOT']);d=r/'package';c=r/'combined';name=sys.argv[1];args=sys.argv[2:]
mode=os.environ['CAL_TEST_MODE']
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(str(v),encoding='utf-8',newline='\n')
def read(p,default=''):return p.read_text() if p.exists() else default
with (r/'events.jsonl').open('a') as f:f.write(json.dumps({'name':name,'args':args})+'\n')
def pid(s):return int(read(r/'services'/s,'0'))
def worker_status(kind,p):put(d/'formal-worker.status',kind+'\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid='+str(p)+'\n')
if name=='id':print(0)
elif name=='stat':print('0:700')
elif name=='health':print('system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0')
elif name=='selfcheck':print('sync-hook-selftest: own=10 forwarded=10 status=1 hardware=0')
elif name=='sleep':
 if not args[0].isdigit():sys.exit(93)
 if (d/'formal-stop.request').exists() and mode!='no_stop_ack':worker_status('formal-worker-stopped-default-off',pid('msg2dbus-farm'))
 if (d/'formal-enable.ready').exists() and not (d/'formal-stop.request').exists() and mode!='enable_fail':put(d/'formal-enable.confirmed','ready')
elif name=='systemctl':
 op=args[0];s=args[-1]
 if op=='show':print('MainPID='+str(pid(s)))
 elif op=='is-active':
  services=[a for a in args[1:] if not a.startswith('-')]
  for service in services:
   if '--quiet' not in args:print('active' if pid(service) else 'inactive')
  sys.exit(0 if all(pid(service) for service in services) else 3)
 elif op=='stop':put(r/'services'/s,0)
 elif op=='start':
  n=int(read(r/'counter','300'))+1;put(r/'counter',n);put(r/'services'/s,n)
  lib='libhbl-formal.so' if s=='victory-gui' else 'libhbl-formal-observer.so'
  put(r/'proc'/str(n)/'maps',str(d/lib).replace('\\','/')+'\n')
  new=(d/lib).read_bytes().startswith(b'new')
  if s=='victory-gui':
   put(d/'formal-ui.sock','socket')
   put(d/'formal-runtime.status','formal-ui-loaded-default-off')
   put(c/'ui.status','ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1 pid='+str(n))
   put(c/'replay.status','replay-page-ready-resources7-components7-pages2 pid='+str(n))
   if mode=='gui_fail' and new:sys.exit(5)
  else:
   worker_status('formal-worker-ready-default-off',n)
   put(d/'formal-worker.sock','socket');put(d/'formal-observer.status','stage=ready meta=1 observe=1')
   if mode=='observer_fail' and new:put(d/'formal-observer.status','failed')
 else:sys.exit(91)
else:sys.exit(92)
'''
def run_case(mode,resume=False):
    root=OUT/(('resume-' if resume else '')+mode);d=root/'package';u=root/'update';c=root/'combined';bin=root/'bin'
    root.mkdir(parents=True);d.mkdir();u.mkdir();c.mkdir();bin.mkdir()
    write(root/'fake.py',FAKE)
    def wrapper(name):return '#!/bin/sh\nexec '+shlex.quote(Path(sys.executable).as_posix())+' '+shlex.quote((root/'fake.py').as_posix())+' '+name+' "$@"\n'
    for name in ('id','stat','sleep','systemctl'):write(bin/name,wrapper(name))
    write(d/'formal-system-check',wrapper('health'));write(d/'formal-sync-hook-check',wrapper('selfcheck'))
    for name in ('formal-ui.rcc','libhbl-formal.so','libhbl-formal-observer.so'):write(d/name,'old-'+name)
    members=['formal-system-check','formal-sync-hook-check','formal-ui.rcc','libhbl-formal.so','libhbl-formal-observer.so']
    def manifest(folder):return ''.join(sha((folder/name).read_bytes())+'  '+name+'\n' for name in sorted(members))
    old=manifest(d);write(d/'manifest.sha256',old)
    write(c/'combined-ui.rcc',(d/'formal-ui.rcc').read_bytes())
    for name in ('install-complete','hold.release'):write(d/'formal-state'/name,'')
    write(d/'formal-state/package-manifest.sha256',sha(old.encode())+'\n')
    for name in ('formal-enable.ready','formal-enable.confirmed'):write(d/name,'ready')
    write(d/'formal-worker.status','formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=202\n')
    write(root/'services/victory-gui','101');write(root/'services/msg2dbus-farm','202')
    for name in members:write(u/name,(d/name).read_bytes())
    for name in ('formal-ui.rcc','libhbl-formal.so','libhbl-formal-observer.so'):write(u/name,'new-'+name)
    new=manifest(u);write(u/'manifest.sha256',new);write(u/'package-manifest.sha256',sha(new.encode())+'\n')
    if resume:
        for name in ('formal-ui.rcc','libhbl-formal.so','libhbl-formal-observer.so','manifest.sha256'):write(u/'previous'/name,(d/name).read_bytes())
        write(u/'previous/package-manifest.sha256',(d/'formal-state/package-manifest.sha256').read_bytes())
        write(d/'formal-stop.request','stop')
        write(d/'formal-worker.status','formal-worker-stopped-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=202\n')
        if mode=='bad_previous':write(u/'previous/libhbl-formal.so','unrecognized')
    script=(WORK/('resume.sh' if resume else 'apply.sh')).read_text(encoding='utf-8')
    script=script.replace('e52e3304080bee4e6767137d18498e9c289d6317bfa962e7fc1e44d2766b00ab',sha(old.encode()))
    for source,target in [('/tmp/hbl-wireless-flash',d),('/tmp/hbl-calibration-r1',u),('/run/hbl-four-module',c),('/proc',root/'proc')]:script=script.replace(source,target.as_posix())
    script=script.replace('[ -S ', '[ -f ').replace(' LD_PRELOAD=', ' TEST_PRELOAD=')
    if mode=='partial_copy':script=script.replace('cp formal-ui.rcc libhbl-formal.so libhbl-formal-observer.so manifest.sha256 "$d/"','cp formal-ui.rcc "$d/"; false')
    write(u/'apply.sh',script)
    write(u/'update.sha256',''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(u.iterdir()) if p.is_file()))
    if mode=='tampered':write(u/'libhbl-formal.so','tampered')
    posix_bin='/'+bin.drive[0].lower()+bin.as_posix()[2:]
    env=dict(os.environ,CAL_TEST_ROOT=str(root),CAL_TEST_MODE=mode,CAL_TEST_BIN=posix_bin,CAL_TEST_APPLY=(u/'apply.sh').as_posix(),MSYS2_ARG_CONV_EXCL='*')
    result=subprocess.run([SHELL,'-c','PATH="$CAL_TEST_BIN:$PATH"; export PATH; sh "$CAL_TEST_APPLY"'],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    write(root/'result.json',json.dumps({'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2))
    if mode=='normal':
        assert result.returncode==0,(mode,result.stderr)
        assert (u/'result').read_text().strip()=='calibration-increment-ready'
        assert (d/'manifest.sha256').read_text()==new
    else:
        assert result.returncode!=0,mode
        assert (d/'manifest.sha256').read_text()==old,mode
        for name in ('formal-ui.rcc','libhbl-formal.so','libhbl-formal-observer.so'):assert (d/name).read_text()=='old-'+name,(mode,name)
    assert (c/'combined-ui.rcc').read_bytes()==(d/'formal-ui.rcc').read_bytes()
    return {'case':mode,'passed':True,'exit':result.returncode}
if __name__=='__main__':
    resume=sys.argv[1:]==['--resume-only']
    modes=('normal','bad_previous','partial_copy','gui_fail') if resume else ('normal','tampered','no_stop_ack','partial_copy','gui_fail','observer_fail','enable_fail')
    cases=[run_case(mode,resume) for mode in modes]
    proof={'passed':True,'applySha256':sha((WORK/('resume.sh' if resume else 'apply.sh')).read_bytes()),'cases':cases,'hardwareRequests':0}
    (HERE/('resume-transaction-validation.json' if resume else 'increment-transaction-validation.json')).write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))
