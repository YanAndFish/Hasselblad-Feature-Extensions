"""执行原样事务 shell 的路径映射副本；服务/进程/UID/原生健康为替身。"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
SRC=HERE/'session'
SHELL=Path('C:/Program Files/Git/bin/sh.exe')
NAMES=('common.sh','install.sh','restore.sh','run.sh')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v if isinstance(v,bytes) else v.encode())
FAKE=r'''
from pathlib import Path
import json,os,sys,shutil
r=Path(os.environ['UI_TEST_ROOT']);d=r/'package';cmd=sys.argv[1];a=sys.argv[2:]
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v)
def flag(n):return (r/n).exists()
with (r/'calls.jsonl').open('a') as f:f.write(json.dumps([cmd]+a)+'\n')
states=json.loads((r/'services.json').read_text())
if cmd=='id':print('0')
elif cmd=='stat':print('0:700' if a[1]=='%u:%a' else '0:1')
elif cmd=='sleep':pass
elif cmd=='ui-health':
 if a==['--self-test']:print('ui-health-self-test-pass')
 elif a==['--require-ready']:
  if flag('bad-health') or (flag('bad-installed-health') and (r/'run/systemd/system/victory-gui.service.d/90-hbl-ui-resident.conf').exists()):sys.exit(1)
  print('ui-health-ready pid='+str(states['victory-gui']['pid'])+' system=2 power=0')
 else:raise ValueError(a)
elif cmd=='systemctl':
 def drops(role):return sorted((r/('run/systemd/system/'+role+'.service.d')).glob('*.conf'))
 if a[0]=='daemon-reload':pass
 elif a[0]=='show':
  role=a[-1];prop=a[2];st=states[role]
  val={'MainPID':str(st['pid']),'FragmentPath':'/lib/systemd/system/'+role+'.service',
       'DropInPaths':' '.join(p.as_posix() for p in drops(role)),'Environment':''}[prop]
  print(prop+'='+val)
 elif a[0]=='is-active':sys.exit(0 if all(states[v]['active'] for v in a[1:] if v!='--quiet') else 3)
 elif a[0] in ('stop','start','restart'):
  assert a[1:]==['victory-gui'],'unexpected service mutation'
  st=states['victory-gui'];old=r/'proc'/str(st['pid'])
  if a[0] in ('stop','restart'):
   if old.exists():old.resolve().relative_to(r.resolve());shutil.rmtree(old)
   st['active']=False
  if a[0]!='stop':
   text=''.join(p.read_text() for p in drops('victory-gui'))
   if text and flag('fail-start'):
    (r/'services.json').write_text(json.dumps(states));sys.exit(1)
   st['pid']+=1000;st['active']=True
   p=r/'proc'/str(st['pid']);write(p/'maps',text);write(p/'environ','')
   if text:
    if not flag('missing-status'):write(d/'ui.status',('ui-resident-component-failed' if flag('bad-component') else 'ui-resident-ready-resources4-components4')+' pid='+str(st['pid']-(1 if flag('stale-pid') else 0))+'\n')
  (r/'services.json').write_text(json.dumps(states))
 else:raise ValueError(a)
else:raise ValueError(cmd)
'''
def fixture(parent,name):
    r=parent/name;d=r/'package';(d/'phases').mkdir(parents=True)
    (r/'run/systemd/system').mkdir(parents=True)
    write(r/'fake.py',FAKE)
    wrapper='#!/bin/sh\nexec "$UI_TEST_PYTHON" "$UI_TEST_FAKE" '
    for n in ('id','stat','sleep','systemctl'):write(r/'bin'/n,wrapper+n+' "$@"\n')
    write(d/'ui-health',wrapper+'ui-health "$@"\n')
    for n in NAMES:
        v=(SRC/n).read_text(encoding='utf-8')
        for old,new in {'/tmp/hbl-ui-resident':d.as_posix(),'/run/systemd/system':(r/'run/systemd/system').as_posix(),
            '/etc/systemd/system':(r/'etc/systemd/system').as_posix(),
            '/proc/':(r/'proc').as_posix()+'/', '/etc/ld.so.preload':(r/'etc/ld.so.preload').as_posix()}.items():v=v.replace(old,new)
        write(d/n,v)
    states={name:{'pid':101+i,'active':True} for i,name in enumerate(('victory-gui','msg2dbus-farm','configstore','jpeg-daemon','storage-daemon'))}
    write(r/'services.json',json.dumps(states));baseline=[]
    for role,st in states.items():
        write(r/'proc'/str(st['pid'])/'environ','');write(r/'proc'/str(st['pid'])/'maps','')
        p=r/'usr/bin'/role;write(p,role+' original');baseline.append(sha(p)+'  '+p.as_posix())
    write(d/'baseline.sha256','\n'.join(baseline)+'\n')
    for n in ('libhbl-ui-resident.so','ui-resident.rcc'):write(d/n,'model '+n)
    write(d/'manifest.sha256',''.join(sha(p)+'  '+p.name+'\n' for p in sorted(d.iterdir()) if p.is_file()))
    e=dict(os.environ,UI_TEST_ROOT=str(r),UI_TEST_PYTHON=sys.executable,UI_TEST_FAKE=str(r/'fake.py'),
        UI_TEST_BIN='/'+r.drive[0].lower()+(r/'bin').as_posix()[2:],MSYS_NO_PATHCONV='1',PYTHONDONTWRITEBYTECODE='1')
    return r,d,e
def run():
    assert Path.cwd().resolve()==ROOT
    parent=HERE/'build/session/tests'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');parent.mkdir(parents=True)
    checks=[]
    def check(n,v,resp=None):
        if not v:raise AssertionError((n,None if resp is None else (resp.returncode,resp.stdout,resp.stderr)))
        checks.append(n)
    def call(d,e,phase):return subprocess.run([str(SHELL),'-c','PATH="$UI_TEST_BIN:/usr/bin:/bin";export PATH;exec sh "$@"','ui-test',str(d/'run.sh'),phase],cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=60)
    def good(d,e,phase):
        resp=call(d,e,phase);check(phase+' passed',resp.returncode==0,resp)
    def calls(r):return [json.loads(v) for v in (r/'calls.jsonl').read_text().splitlines()]
    def mutations(r):return [v for v in calls(r) if v[0]=='systemctl' and v[1] in ('stop','start','restart')]
    for n in NAMES:subprocess.run([str(SHELL),'-n',str(SRC/n)],check=True)
    r,d,e=fixture(parent,'normal');good(d,e,'preflight')
    check('preflight no service mutation',not mutations(r) and not (d/'state').exists())
    good(d,e,'ui');good(d,e,'status');good(d,e,'status')
    check('only one GUI restart',mutations(r)==[['systemctl','restart','victory-gui']])
    check('duplicate UI rejected',call(d,e,'ui').returncode==62)
    good(d,e,'restore');check('original restoration',mutations(r)==[['systemctl','restart','victory-gui'],['systemctl','stop','victory-gui'],['systemctl','start','victory-gui']] and (d/'state/restored.done').exists())
    for flag in ('fail-start','bad-component','missing-status','stale-pid','bad-installed-health'):
        r,d,e=fixture(parent,flag);write(r/flag,'1');resp=call(d,e,'ui')
        check(flag+' automatically restored',resp.returncode==64 and (d/'state/restored.done').exists() and 'ui-resident-install-failed-original-restored' in resp.stdout,resp)
    for role in ('victory-gui','msg2dbus-farm','configstore','jpeg-daemon'):
        r,d,e=fixture(parent,'foreign-'+role);p=r/('run/systemd/system/'+role+'.service.d/80-replay.conf');write(p,'foreign session')
        resp=call(d,e,'ui');check(role+' foreign dropin preserved',resp.returncode==61 and not mutations(r) and p.read_text()=='foreign session',resp)
    r,d,e=fixture(parent,'tampered');write(d/'ui-resident.rcc','bad')
    check('tampered package no services',call(d,e,'ui').returncode==60 and not mutations(r))
    r,d,e=fixture(parent,'baseline');write(r/'usr/bin/victory-gui','bad')
    check('baseline mismatch no services',call(d,e,'ui').returncode==60 and not mutations(r))
    r,d,e=fixture(parent,'health');write(r/'bad-health','1')
    check('unhealthy original untouched',call(d,e,'ui').returncode==62 and not mutations(r))
    r,d,e=fixture(parent,'lock');(d/'phase.lock').mkdir()
    check('concurrent phase refused',call(d,e,'ui').returncode==62 and (d/'phase.lock').is_dir() and not mutations(r))
    r,d,e=fixture(parent,'unknown');write(d/'phases/preflight.sent','sent')
    check('unknown earlier outcome refuses new UI',call(d,e,'ui').returncode==62 and not mutations(r))
    for name in ('changed-owned','new-foreign'):
        r,d,e=fixture(parent,name);good(d,e,'ui');before=mutations(r)
        p=r/('run/systemd/system/victory-gui.service.d/'+('90-hbl-ui-resident.conf' if name=='changed-owned' else '99-foreign.conf'))
        write(p,'foreign');resp=call(d,e,'restore')
        check(name+' restoration preserves foreign ownership',resp.returncode==66 and mutations(r)==before and p.read_text()=='foreign',resp)
    source={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(SRC.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    proof={'passed':True,'checks':checks,'sources':source,'testSha256':sha(Path(__file__)),
        'hardwareRequests':0,'targetValidated':False,'scope':'actual shell and file hashes; process/service/native health/UID are mocks'}
    write(HERE/'build/session/install-validation.json',json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
