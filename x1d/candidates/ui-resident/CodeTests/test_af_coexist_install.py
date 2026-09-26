"""保留 AF r4 的真实 shell 事务；仅服务/进程/权限/socket/健康为替身。"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2];SRC=HERE/'af-session'
SHELL=Path('C:/Program Files/Git/bin/sh.exe');NAMES=('common.sh','install.sh','restore.sh','run.sh')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v if isinstance(v,bytes) else v.encode())
FAKE=r'''
from pathlib import Path
import json,os,sys,shutil,shlex
r=Path(os.environ['AF_UI_TEST_ROOT']);d=r/'package';af=r/'af';r4=r/'r4';sock=r/'sockets';cmd=sys.argv[1];a=sys.argv[2:]
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v if isinstance(v,bytes) else v.encode())
def flag(n):return (r/n).exists()
with (r/'calls.jsonl').open('a') as f:f.write(json.dumps([cmd]+a)+'\n')
states=json.loads((r/'services.json').read_text())
if cmd=='ui-health':
 if a==['--self-test']:print('ui-health-self-test-pass')
 elif a==['--require-ready']:
  if flag('bad-health'):sys.exit(1)
  print('ui-health-ready pid='+str(states['victory-gui']['pid'])+' system=4 power=1')
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
  assert a[1:]==['victory-gui'],'AF bus or protected service mutation'
  st=states['victory-gui'];old=r/'proc'/str(st['pid'])
  if a[0] in ('stop','restart'):
   if old.exists():old.resolve().relative_to(r.resolve());shutil.rmtree(old)
   st['active']=False
  if a[0]!='stop':
   environment={}
   for f in drops('victory-gui'):
    for line in f.read_text().splitlines():
     if line.startswith('Environment='):
      for value in shlex.split(line.split('=',1)[1]):
       key,val=value.split('=',1);environment[key]=val
   text=environment.get('LD_PRELOAD','');integrated='libhbl-ui-af.so' in text
   if (integrated and flag('fail-start')) or (sock/'ui.sock').exists():
    (r/'services.json').write_text(json.dumps(states));sys.exit(1)
   st['pid']+=1000;st['active']=True
   p=r/'proc'/str(st['pid']);write(p/'maps',text)
   write(p/'environ',b'\0'.join((k+'='+v).encode() for k,v in environment.items())+b'\0')
   write(sock/'ui.sock','new GUI socket');write(af/'ui.status','af-only-ui-ready\n')
   write(sock/'ui-r4.status','stage=ready pid='+str(st['pid'])+' bound='+('0' if integrated and flag('bad-r4-bound') else '1')+' shown=0 width=0 height=0 connected=0 reading=0 applying=0 paused=0 queries=0 applies=0 replies=0 envelope=0 config=0 lens=0 socket=0 timeouts=0 sendfail=0 edits=0\n')
   if integrated:
    if flag('change-bus'):states['msg2dbus-farm']['pid']+=5000
    state='ui-af-component-failed' if flag('bad-component') else 'ui-af-ready-resources10-components8-contexts2'
    write(d/'ui.status',state+' pid='+str(st['pid'])+'\n')
  (r/'services.json').write_text(json.dumps(states))
 else:raise ValueError(a)
else:raise ValueError(cmd)
'''
def fixture(parent,name):
    r=parent/name;d=r/'package';af=r/'af';r4=r/'r4';sock=r/'sockets'
    for p in (d/'phases',af/'install-state',r4,sock,r/'run/systemd/system'):p.mkdir(parents=True,exist_ok=True)
    write(r/'fake.py',FAKE)
    write(r/'calls.jsonl','')
    wrapper='#!/bin/sh\nexec "$AF_UI_TEST_PYTHON" "$AF_UI_TEST_FAKE" '
    write(r/'bin/systemctl',wrapper+'systemctl "$@"\n');write(d/'ui-health',wrapper+'ui-health "$@"\n')
    write(r/'bin/id','#!/bin/sh\nprintf "0\\n"\n')
    write(r/'bin/stat','#!/bin/sh\nif [ "$2" = "%u:%a" ];then case "$3" in *.sock) printf "0:600\\n";; *) printf "0:700\\n";;esac;else printf "0:1\\n";fi\n')
    write(r/'bin/sleep','#!/bin/sh\nexit 0\n')
    for n in NAMES:
        v=(SRC/n).read_text(encoding='utf-8')
        for old,new in {'/tmp/hbl-ui-af':d.as_posix(),'/tmp/hbl-x1d-combined':af.as_posix(),'/tmp/hbl-af-ui-r4':r4.as_posix(),
            '/tmp/hbl-af-settings':sock.as_posix(),'/run/systemd/system':(r/'run/systemd/system').as_posix(),
            '/etc/systemd/system':(r/'etc/systemd/system').as_posix(),'/proc/':(r/'proc').as_posix()+'/',
            '/etc/ld.so.preload':(r/'etc/ld.so.preload').as_posix()}.items():v=v.replace(old,new)
        write(d/n,v.replace('[ -S ','[ -f '))
    states={name:{'pid':101+i,'active':True} for i,name in enumerate(('victory-gui','msg2dbus-farm','configstore','jpeg-daemon','storage-daemon'))}
    oldpreload=af.as_posix()+'/libhbl-af-only.so:'+r4.as_posix()+'/libhbl-af-ui.so'
    gui90='[Service]\nRestart=no\nUMask=0077\nEnvironment=HBL_AF_ONLY_ENABLE=1\nEnvironment=HBL_AF_ONLY_HOLD=1\nEnvironment=HBL_AF_SETTINGS_ENABLE=1\nEnvironment=LD_PRELOAD='+af.as_posix()+'/libhbl-af-only.so:'+af.as_posix()+'/af/libhbl-af-ui.so\n'
    gui95='[Service]\nEnvironment=HBL_AF_UI_R4_ENABLE=1\nEnvironment=LD_PRELOAD='+oldpreload+'\n'
    bus90='[Service]\nRestart=no\nUMask=0077\nEnvironment=HBL_AF_SETTINGS_ENABLE=1\nEnvironment=LD_PRELOAD='+af.as_posix()+'/af/libhbl-af-bus.so\n'
    for n,text,path in [('af-gui.expected',gui90,'victory-gui.service.d/90-hbl-af-only.conf'),('r4-gui.expected',gui95,'victory-gui.service.d/95-hbl-af-ui-r4.conf'),('af-bus.expected',bus90,'msg2dbus-farm.service.d/90-hbl-af-only.conf')]:
        write(d/n,text);write(r/'run/systemd/system'/path,text)
    for n,v in {'owner':'hbl-af-only-v1\n','hold.release':'release','af-installed.sha256':'b'*64+'\n','release.done':'','ram.started':'started'}.items():write(af/'install-state'/n,v)
    write(d/'af-receipt.expected','b'*64+'\n')
    write(sock/'backend.sock','AF backend socket');write(sock/'ui.sock','old GUI socket');write(sock/'backend-r2.status','stage=ready error=0 meta=1 uart=1\n')
    write(af/'ui.status','af-only-ui-ready\n');write(r/'af-ram-model','installed AF RAM - do not touch')
    write(sock/'ui-r4.status','stage=ready pid=101 bound=1 shown=0 width=0 height=0 connected=0 reading=0 applying=0 paused=0 queries=0 applies=0 replies=0 envelope=0 config=0 lens=0 socket=0 timeouts=0 sendfail=0 edits=0\n')
    for n in ('libhbl-af-only.so','af/libhbl-af-ui.so','af/libhbl-af-bus.so','af-only-ui.rcc'):write(af/n,'fixed '+n)
    for n in ('libhbl-af-ui.so','af-only-ui.rcc'):write(r4/n,'fixed r4 '+n)
    inherited=[af/n for n in ('libhbl-af-only.so','af/libhbl-af-ui.so','af/libhbl-af-bus.so','af-only-ui.rcc')]+[r4/n for n in ('libhbl-af-ui.so','af-only-ui.rcc')]
    write(d/'inherited.sha256',''.join(sha(p)+'  '+p.as_posix()+'\n' for p in inherited))
    baseline=[]
    for role,st in states.items():
        env={}
        if role=='victory-gui':env={'HBL_AF_ONLY_ENABLE':'1','HBL_AF_ONLY_HOLD':'1','HBL_AF_SETTINGS_ENABLE':'1','HBL_AF_UI_R4_ENABLE':'1','LD_PRELOAD':oldpreload}
        if role=='msg2dbus-farm':env={'HBL_AF_SETTINGS_ENABLE':'1','LD_PRELOAD':af.as_posix()+'/af/libhbl-af-bus.so'}
        write(r/'proc'/str(st['pid'])/'environ',b'\0'.join((k+'='+v).encode() for k,v in env.items())+b'\0')
        write(r/'proc'/str(st['pid'])/'maps',env.get('LD_PRELOAD',''))
        p=r/'usr/bin'/role;write(p,'original '+role);baseline.append(sha(p)+'  '+p.as_posix())
    write(r/'services.json',json.dumps(states));write(d/'baseline.sha256','\n'.join(baseline)+'\n')
    for n in ('libhbl-ui-af.so','ui-af.rcc'):write(d/n,'model '+n)
    write(d/'manifest.sha256',''.join(sha(p)+'  '+p.name+'\n' for p in sorted(d.iterdir()) if p.is_file()))
    env=dict(os.environ,AF_UI_TEST_ROOT=str(r),AF_UI_TEST_PYTHON=sys.executable,AF_UI_TEST_FAKE=str(r/'fake.py'),
        AF_UI_TEST_BIN='/'+r.drive[0].lower()+(r/'bin').as_posix()[2:],MSYS_NO_PATHCONV='1',PYTHONDONTWRITEBYTECODE='1')
    protected={p:sha(p) for p in [*inherited,r/'af-ram-model',sock/'backend.sock',r/'proc/102/environ',r/'proc/102/maps',*list((af/'install-state').iterdir()),*list((r/'run/systemd/system').rglob('*.conf'))]}
    return r,d,env,protected
def run():
    assert Path.cwd().resolve()==ROOT
    parent=HERE/'build/af-session/transaction-tests'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');parent.mkdir(parents=True)
    checks=[]
    def check(n,v,response=None):
        if not v:raise AssertionError((n,None if response is None else (response.returncode,response.stdout,response.stderr)))
        checks.append(n);print(json.dumps({'check':n,'passed':True}),flush=True)
    def call(d,e,phase):return subprocess.run([str(SHELL),'-c','PATH="$AF_UI_TEST_BIN:/usr/bin:/bin";export PATH;exec sh "$@"','af-ui-test',str(d/'run.sh'),phase],cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=180)
    def good(d,e,phase):
        response=call(d,e,phase);check(phase+' passed',response.returncode==0,response)
    def calls(r):return [json.loads(v) for v in (r/'calls.jsonl').read_text().splitlines()]
    def actions(r):return [v for v in calls(r) if v[0]=='systemctl' and v[1] in ('start','stop','restart')]
    def preserved(values):return all(p.exists() and sha(p)==v for p,v in values.items())
    for n in NAMES:subprocess.run([str(SHELL),'-n',str(SRC/n)],check=True)
    r,d,e,p=fixture(parent,'normal');good(d,e,'preflight');check('standby preflight changes no service',not actions(r))
    good(d,e,'ui');good(d,e,'status');check('integration preserves AF files RAM bus and old dropins',preserved(p))
    check('duplicate UI rejected',call(d,e,'ui').returncode==62)
    good(d,e,'restore');check('rollback returns AF r4 without bus restart',preserved(p) and actions(r)==[['systemctl','stop','victory-gui'],['systemctl','start','victory-gui']]*2)
    for fail in ('fail-start','bad-component','bad-r4-bound'):
        r,d,e,p=fixture(parent,fail);write(r/fail,'1');response=call(d,e,'ui')
        check(fail+' automatically returns to AF r4',response.returncode==64 and (d/'state/restored.done').exists() and preserved(p),response)
    for name in ('wrong-r4','hold-not-released','wrong-af-receipt','foreign-dropin','wrong-preload','r4-applying','r4-stale-pid','r4-malformed'):
        r,d,e,p=fixture(parent,name)
        if name=='wrong-r4':write(r/'r4/libhbl-af-ui.so','unknown')
        elif name=='hold-not-released':write(r/'af/install-state/hold.release','not-released')
        elif name=='wrong-af-receipt':write(r/'af/install-state/af-installed.sha256','c'*64+'\n')
        elif name=='foreign-dropin':write(r/'run/systemd/system/victory-gui.service.d/97-foreign.conf','foreign')
        elif name=='wrong-preload':write(r/'proc/101/environ','LD_PRELOAD=wrong\0')
        else:
            diag=r/'sockets/ui-r4.status';value=diag.read_text()
            value=value.replace('applying=0','applying=1') if name=='r4-applying' else (value.replace('pid=101','pid=99') if name=='r4-stale-pid' else value+'extra=1')
            write(diag,value)
        response=call(d,e,'ui');check(name+' rejected before GUI stop',response.returncode==61 and not actions(r),response)
    r,d,e,p=fixture(parent,'foreign-after');good(d,e,'ui');before=actions(r)
    target=r/'run/systemd/system/victory-gui.service.d/95-hbl-af-ui-r4.conf';write(target,'changed by owner')
    response=call(d,e,'restore');check('changed AF owner config never overwritten',response.returncode==60 and actions(r)==before and target.read_text()=='changed by owner',response)
    r,d,e,p=fixture(parent,'bus-changed');write(r/'change-bus','1');response=call(d,e,'ui')
    check('changed bus identity stops for review without restarting bus',response.returncode==64 and 'recovery-required' in response.stdout and actions(r)==[['systemctl','stop','victory-gui'],['systemctl','start','victory-gui']],response)
    report={'passed':True,'checks':checks,'sources':{(SRC/n).relative_to(ROOT).as_posix():sha(SRC/n) for n in NAMES},'testSha256':sha(Path(__file__)),
        'hardwareRequests':0,'targetValidated':False,'r4FixtureContract':True,'scope':'actual shell, synthetic fixed AF r4 service/process/socket and health'}
    write(HERE/'build/af-session/install-validation.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}),flush=True)
if __name__=='__main__':run()
