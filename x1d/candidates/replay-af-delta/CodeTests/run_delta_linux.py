"""执行实际增量 shell，服务/PID/socket种类/所有者为隔离替身；不访问设备。"""
from pathlib import Path
import json,hashlib,subprocess,sys,os,tempfile
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
OUT=HERE/'artifacts/linux-tests';SHELL='C:/Program Files/Git/bin/sh.exe'
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(b if isinstance(b,bytes) else b.encode())
FAKE=r'''import os,sys,json,shutil
from pathlib import Path
r=Path(os.environ['DELTA_ROOT']);d=r/'delta';af=r/'af';s=r/'settings';cmd=sys.argv[1];a=sys.argv[2:]
def w(p,b):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b if isinstance(b,bytes) else b.encode())
def flag(n):return (r/n).exists()
state=json.loads((r/'processes.json').read_text());role=a[-1] if a else ''
with (r/'commands.jsonl').open('a') as f:f.write(json.dumps([cmd,*a])+'\n')
def drops(role):return sorted((r/'units'/(role+'.service.d')).glob('*.conf'))
def current(role):return state[role]['pid']
if cmd=='id':print(0)
elif cmd=='stat':
 if flag('bad-owner'):print('9:1' if a[1]=='%u:%h' else '9:700')
 elif a[1]=='%u:%h':print('0:1')
 else:print('0:600' if a[-1].endswith('.sock') else '0:700')
elif cmd=='sleep':pass
elif cmd=='systemctl':
 if a[0]=='show':
  key=a[2];value={'LoadState':'loaded','ActiveState':'active' if state[role]['active'] else 'inactive',
   'SubState':'running' if state[role]['active'] else 'dead','MainPID':str(current(role)),
   'FragmentPath':'/lib/systemd/system/'+role+'.service','DropInPaths':' '.join(p.as_posix() for p in drops(role)),
   'Environment':''}[key]
  print(key+'='+value)
 elif a[0]=='is-active':sys.exit(0 if state[role]['active'] else 3)
 elif a[0]=='daemon-reload':pass
 elif a[0] in ('stop','start','restart'):
  assert role=='victory-gui','unexpected service mutation'
  if a[0]=='stop':
   p=r/'proc'/str(current(role));p.resolve().relative_to((r/'proc').resolve())
   if p.exists():shutil.rmtree(p)
   state[role]['active']=False;state[role]['pid']=0
  else:
   if flag('fail-start') and not flag('failed-once'):
    w(r/'failed-once','1');sys.exit(1)
   if flag('restore-fail') and not any(p.name.startswith('95-') for p in drops(role)):sys.exit(1)
   state[role]['pid']=state[role].get('next',450);state[role]['next']=state[role]['pid']+1;state[role]['active']=True
   p=r/'proc'/str(current(role));env={}
   for path in drops(role):
    for line in path.read_text().splitlines():
     if line.startswith('Environment='):
      k,v=line[12:].split('=',1);env[k]=v
   w(p/'exe',(r/'bin-original/victory-gui').read_bytes());w(p/'maps','\n'.join(env['LD_PRELOAD'].replace(':C:/','|C:/').split('|'))+'\n')
   w(p/'environ','\0'.join(k+'='+v for k,v in env.items())+'\0')
   w(af/'ui.status','af-only-ui-ready\n');w(s/'ui.sock','mock-socket')
   w(s/'ui-r4.status','stage=ready pid='+str(current(role))+' bound=1 shown=0 width=0 height=0 connected=0 reading=0 applying=0 paused=0\n')
  (r/'processes.json').write_text(json.dumps(state))
 else:raise AssertionError(a)
elif cmd=='replay-check':
 if a[0]=='--begin':w(d/'state/deadline','RPD1 100000\n')
 elif a[0]=='--owners':assert a[1:]==['101','303','202']
 elif a[0]=='--gpu':
  if flag('bad-gpu'):sys.exit(67)
  if not (d/'state/deadline').exists() or (d/'state/release').exists():sys.exit(67)
 elif a[0]=='--active' and flag('sleeping'):sys.exit(66)
 elif a[0] not in ('--active','--selftest'):raise AssertionError(a)
 print('mock-active')
else:raise AssertionError(cmd)
'''
def fixture(name):
    r=Path(tempfile.mkdtemp(prefix=name+'-',dir=OUT));d=r/'delta';af=r/'af';s=r/'settings'
    for p in (d,af/'install-state',s,r/'units',r/'proc'):p.mkdir(parents=True,exist_ok=True)
    write(r/'fake.py',FAKE)
    maps={'/tmp/hbl-x1d-rpa':d.as_posix(),'/tmp/hbl-x1d-combined':af.as_posix(),
          '/tmp/hbl-af-settings':s.as_posix(),'/run/systemd/system':(r/'units').as_posix(),
          '/proc/':(r/'proc').as_posix()+'/', '/usr/bin/':(r/'bin-original').as_posix()+'/',
          '/etc/ld.so.preload':(r/'ld.so.preload').as_posix()}
    def translate(text):
        for a,b in maps.items():text=text.replace(a,b)
        return text
    for p in (HERE/'artifacts/package-staging').iterdir():
        if p.name in ('draft.json','manifest.sha256','baseline.sha256','af-files.sha256'):continue
        b=p.read_bytes()
        if p.suffix in ('.sh','.conf'):b=translate(b.decode()).encode()
        if p.name=='common.sh':
            text=b.decode().replace('[ -S "$settings/backend.sock" ]','[ -f "$settings/backend.sock" ]').replace('[ -S "$settings/ui.sock" ]','[ -f "$settings/ui.sock" ]')
            text=text.replace('^\\/(usr\\/bin|usr\\/lib|lib)\\/', '^'+r.as_posix().replace('/','\\/')+'\\/bin-original\\/')
            b=text.encode()
        write(d/p.name,b)
    for command in ('id','stat','systemctl','sleep','replay-check'):
        write((d if command=='replay-check' else r/'fake-bin')/command,'#!/bin/sh\nexec "$DELTA_PYTHON" "$DELTA_FAKE" '+command+' "$@"\n')
    processes={};baseline=[]
    for role,pid in [('configstore',101),('jpeg-daemon',303),('storage-daemon',202),('msg2dbus-farm',305),('victory-gui',404)]:
        exe='msg2dbus' if role=='msg2dbus-farm' else role;b=('original-'+exe).encode();write(r/'bin-original'/exe,b)
        write(r/'proc'/str(pid)/'exe',b);write(r/'proc'/str(pid)/'maps','');write(r/'proc'/str(pid)/'environ','')
        baseline.append(sha(b)+'  '+(r/'bin-original'/exe).as_posix());processes[role]={'pid':pid,'active':True}
    write(d/'baseline.sha256','\n'.join(baseline)+'\n');write(r/'processes.json',json.dumps(processes))
    write(r/'units/victory-gui.service.d/90-hbl-af-only.conf',(d/'gui.af.conf').read_bytes())
    write(r/'units/msg2dbus-farm.service.d/90-hbl-af-only.conf',(d/'bus.af.conf').read_bytes())
    for n in ('libhbl-af-only.so','af/libhbl-af-ui.so','af/libhbl-af-bus.so','af-only-ui.rcc'):write(af/n,'fixture-'+n)
    afmanifest=''.join(sha(p.read_bytes())+'  '+p.relative_to(af).as_posix()+'\n' for p in sorted(af.rglob('*')) if p.is_file())
    write(af/'manifest.sha256',afmanifest)
    write(d/'af-files.sha256',''.join(sha(p.read_bytes())+'  '+p.as_posix()+'\n' for p in sorted(af.rglob('*')) if p.is_file()))
    for n,b in {'owner':'hbl-af-only-v1\n','package.sha256':sha(afmanifest.encode())+'\n',
                'gui.dropin':(d/'gui.af.conf').read_bytes(),'farm.dropin':(d/'bus.af.conf').read_bytes(),
                'af-installed.sha256':(d/'af-proof.txt').read_bytes(),'ram.started':'started','hold.release':'release',
                'ui.done':'','bus.done':'','release.done':''}.items():write(af/'install-state'/n,b)
    write(s/'backend.sock','mock-socket');write(s/'ui.sock','mock-socket')
    write(s/'backend-r3.status','stage=ready error=0 meta=1 uart=1\n');write(af/'ui.status','af-only-ui-ready\n')
    write(s/'ui-r4.status','stage=ready pid=404 bound=1 shown=0 width=0 height=0 connected=0 reading=0 applying=0 paused=0\n')
    for role,pid,conf in [('victory-gui',404,'gui.af.conf'),('msg2dbus-farm',305,'bus.af.conf')]:
        env=[line[12:] for line in (d/conf).read_text().splitlines() if line.startswith('Environment=')]
        write(r/'proc'/str(pid)/'environ','\0'.join(env)+'\0')
        preload=next(v[11:] for v in env if v.startswith('LD_PRELOAD='));write(r/'proc'/str(pid)/'maps','\n'.join(preload.replace(':C:/','|C:/').split('|'))+'\n')
    write(d/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(d.iterdir()) if p.is_file()))
    env=dict(os.environ,DELTA_ROOT=str(r),DELTA_PYTHON=sys.executable,DELTA_FAKE=str(r/'fake.py'),
             DELTA_BIN='/'+r.drive[0].lower()+(r/'fake-bin').as_posix()[2:],MSYS_NO_PATHCONV='1',PYTHONDONTWRITEBYTECODE='1')
    return r,d,env
def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[]
    # Windows 每次替身调用都启动 Python/MSYS；此上限不是目标机等待时间。
    def call(d,e,n):return subprocess.run([SHELL,'-c','PATH="$DELTA_BIN:/usr/bin:/bin";export PATH;exec sh "$1"','delta-test',str(d/n)],cwd=ROOT,env=e,capture_output=True,text=True,timeout=600)
    def mutations(r):
        rows=[json.loads(s) for s in (r/'commands.jsonl').read_text().splitlines()]
        edits=[x for x in rows if x[0]=='systemctl' and x[1] in ('start','stop','restart')]
        assert all(x[2]=='victory-gui' for x in edits),edits
        return edits
    def ok(name,condition,result=None):
        assert condition,(name,result.stdout+result.stderr if result else '')
        cases.append(name);print(name,flush=True)
    r,d,e=fixture('normal');before=sha((r/'af/manifest.sha256').read_bytes())
    result=call(d,e,'preflight.sh');ok('preflight-no-service-change',result.returncode==0 and not mutations(r),result)
    result=call(d,e,'install.sh');ok('one-gui-stop-start-and-original-af-preserved',result.returncode==0 and mutations(r)==[['systemctl','stop','victory-gui'],['systemctl','start','victory-gui']],result)
    ok('af-hold-remains-released', (r/'af/install-state/hold.release').read_text()=='release' and (d/'state/release').exists())
    result=call(d,e,'restore.sh');ok('restore-to-af-only',result.returncode==0 and (d/'state/restored').exists(),result)
    prior=mutations(r);result=call(d,e,'restore.sh');ok('repeat-restore-no-service-change',result.returncode==0 and mutations(r)==prior,result)
    ok('af-manifest-and-bus-pid-unchanged',before==sha((r/'af/manifest.sha256').read_bytes()) and json.loads((r/'processes.json').read_text())['msg2dbus-farm']['pid']==305)
    for flag in ('sleeping','bad-owner','busy-ui','changed-af'):
        r,d,e=fixture(flag)
        if flag=='busy-ui':p=r/'settings/ui-r4.status';write(p,p.read_text().replace('applying=0','applying=1'))
        elif flag=='changed-af':write(r/'af/af/libhbl-af-bus.so','changed')
        else:write(r/flag,'1')
        result=call(d,e,'install.sh');ok(flag+'-no-mutation',result.returncode!=0 and not mutations(r),result)
    for flag in ('bad-gpu','fail-start'):
        r,d,e=fixture(flag);write(r/flag,'1');result=call(d,e,'install.sh')
        ok(flag+'-restores-af',result.returncode!=0 and (d/'state/restored').exists(),result);mutations(r)
    r,d,e=fixture('foreign');result=call(d,e,'install.sh');assert result.returncode==0,result.stdout+result.stderr
    drop=r/'units/victory-gui.service.d/95-x1d-replay-af.conf';write(drop,'foreign\n');prior=mutations(r)
    result=call(d,e,'restore.sh');ok('foreign-delta-not-removed',result.returncode==73 and drop.read_text()=='foreign\n' and mutations(r)==prior,result)
    report={'passed':True,'cameraAccess':False,'cases':cases,'realServices':False,'socketKindsAndOwnershipMocked':True,
      'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),*sorted((HERE/'session').glob('*.sh'))]}}
    (OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'deltaScriptCases':len(cases),'cameraAccess':False}))
if __name__=='__main__':run()
