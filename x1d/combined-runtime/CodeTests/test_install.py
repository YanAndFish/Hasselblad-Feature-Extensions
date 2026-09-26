"""运行实际组合 shell 工作副本；仅服务、硬件检查和 socket 类型使用替身。"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
SHELL = Path('C:/Program Files/Git/bin/sh.exe')
OUT = HERE / 'CodeTests/output'
SOURCE_NAMES = ('common.sh', 'install.sh', 'restore.sh', 'run.sh')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else value.encode('utf-8'))

FAKE = r'''
import json, os, sys, shutil
from pathlib import Path
r=Path(os.environ['COMBINED_TEST_ROOT']); d=r/'combined'; s=d/'install-state'; a=sys.argv[2:]; cmd=sys.argv[1]
def write(p,t):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.encode())
def flag(n):return (r/n).exists()
with (r/'calls.jsonl').open('a') as f:f.write(json.dumps([cmd]+a)+'\n')
if cmd=='id':print('0')
elif cmd=='stat':
 if a[1]=='%u:%a':print('0:600' if a[2].endswith('.sock') else '0:700')
 elif a[1]=='%u:%h':print('0:1')
 else:raise RuntimeError(a)
elif cmd=='sleep':pass
elif cmd=='system-check':
 if flag('expired') and a[0].startswith('--require-held'):sys.exit(1)
 if a[0]=='--begin-hold':
  with (s/'hold.deadline').open('x') as f:f.write('1200000')
  write(s/'hold.pulse','fresh')
 elif a[0].startswith('--require'):print('system=2 suc=0 farm=0 pwr=0 ui-power=0 hold='+('1' if 'held' in a[0] else '0'))
elif cmd=='replay-joint-check':
 if flag('bad-gpu'):sys.exit(1)
elif cmd in ('formal-sync-hook-check','formal-client-check','formal-netlink-probe'):pass
elif cmd=='formal-prepare-radio':
 write(r/'flash/formal-state/radio-prepared','simulated')
elif cmd=='replay-backend':
 b=d/'replay-state/backend';phase=a[0]
 if phase=='--prepare':write(b/'owner','model')
 elif phase in ('--config','--jpeg'):
  name=phase[2:];write(b/(name+'.done'),'');write(b/(('configstore' if name=='config' else 'jpeg-daemon')+'.touched'),'')
 elif phase=='--restore':write(b/'restore.done','')
 elif phase=='--status':print('replay-backend protected-processes=match')
 else:raise RuntimeError(a)
elif cmd=='systemctl':
 statepath=r/'services.json';states=json.loads(statepath.read_text())
 def save():statepath.write_text(json.dumps(states))
 def drop(role):return r/('run/systemd/system/'+role+'.service.d/90-hbl-combined.conf')
 if a[0]=='daemon-reload':pass
 elif a[0]=='show':
  role=a[-1];st=states[role];props=[a[n+1] for n in range(len(a)-1) if a[n]=='-p']
  for prop in props:
   val={'MainPID':str(st['pid']),'FragmentPath':'/lib/systemd/system/'+role+'.service','DropInPaths':str(drop(role)) if drop(role).exists() else '',
    'ActiveState':'active' if st['active'] else 'inactive','LoadState':'loaded','Environment':''}.get(prop,'')
   print(prop+'='+val)
 elif a[0]=='is-active':
  roles=[v for v in a[1:] if v!='--quiet'];sys.exit(0 if all(states[v]['active'] for v in roles) else 3)
 elif a[0] in ('stop','start','restart'):
  action=a[0]
  for role in a[1:]:
   st=states[role];old=r/'proc'/str(st['pid'])
   if action in ('stop','restart'):
    if old.exists():old.resolve().relative_to(r.resolve());shutil.rmtree(old)
    st['active']=False
   if action=='stop':continue
   text=drop(role).read_text() if drop(role).exists() else ''
   if role=='victory-gui' and flag('fail-provider') and 'libx1d-replay-provider.so' in text:save();sys.exit(1)
   st['pid']+=1000;st['active']=True
   proc=r/'proc'/str(st['pid']);write(proc/'environ','');write(proc/'maps',text)
   if role=='victory-gui' and text:
    write(d/'ui.status','formal-ui-loaded-default-off\n');write(r/'flash/formal-ui.sock','');write(r/'af/ui.sock','')
   if role=='msg2dbus-farm' and text:
    write(r/'flash/formal-observer.status','stage=ready meta=1 observe=1\n')
    write(r/'flash/formal-worker.status','formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid='+str(st['pid'])+'\n')
    write(r/'flash/formal-worker.sock','');write(r/'af/backend.sock','')
  save()
 else:raise RuntimeError(a)
else:raise RuntimeError(cmd)
'''

def fixture(parent, name):
    r = parent / name
    r.mkdir()
    d = r / 'combined'
    (d / 'phases').mkdir(parents=True)
    (r / 'run/systemd/system').mkdir(parents=True)
    write(r / 'fake.py', FAKE)
    wrapper = '#!/bin/sh\nexec "$COMBINED_TEST_PYTHON" "$COMBINED_TEST_FAKE" '
    commands = ('id', 'stat', 'sleep', 'systemctl')
    for name in commands: write(r / 'bin' / name, wrapper + name + ' "$@"\n')
    for name in ('system-check',): write(d / name, wrapper + name + ' "$@"\n')
    for name in ('formal-sync-hook-check', 'formal-client-check', 'formal-netlink-probe'):
        write(d / 'flash' / name, wrapper + name + ' "$@"\n')
    write(d / 'flash/formal-prepare-radio.sh', wrapper + 'formal-prepare-radio "$@"\n')
    write(d / 'flash/libhbl-formal-observer.so', 'model observer')
    write(d / 'flash/delta/0.bin', 'model delta')
    write(d / 'flash/manifest.sha256', ''.join(sha(p)+'  '+p.relative_to(d / 'flash').as_posix()+'\n' for p in sorted((d / 'flash').rglob('*')) if p.is_file()))
    for name in ('af/libhbl-af-ui.so', 'af/libhbl-af-bus.so', 'libhbl-combined.so', 'combined-ui.rcc'):
        write(d / name, 'model ' + name)
    write(d / 'replay/replay-joint-check', wrapper+'replay-joint-check "$@"\n')
    write(d / 'replay/backend.sh', wrapper+'replay-backend "$@"\n')
    for name in ('libx1d-replay-joint.so', 'libx1d-replay-provider.so'):write(d / 'replay' / name, 'model '+name)
    for name in SOURCE_NAMES:
        source = (HERE / name).read_text(encoding='utf-8')
        for original, target in {'/tmp/hbl-x1d-combined':d.as_posix(), '/tmp/hbl-wireless-flash':(r/'flash').as_posix(),
                                 '/tmp/hbl-af-settings':(r/'af').as_posix(), '/run/systemd/system':(r/'run/systemd/system').as_posix(),
                                 '/proc/':(r/'proc').as_posix()+'/', '/etc/ld.so.preload':(r/'etc/ld.so.preload').as_posix()}.items():
            source = source.replace(original, target)
        # Windows 文件替身只能验证生命周期；目标 socket 类型/凭据由 ARM 和实机检查覆盖。
        source = source.replace('[ -S ', '[ -f ')
        source = source.replace('HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD=', 'HBL_FORMAL_SYNC_SELFTEST=1 COMBINED_TEST_PRELOAD=')
        write(d / name, source)
    roles = {'victory-gui':101, 'msg2dbus-farm':202}
    write(r / 'services.json', json.dumps({k:{'pid':v, 'active':True} for k,v in roles.items()}))
    baseline=[]
    for role,p in roles.items():
        write(r/'proc'/str(p)/'environ','');write(r/'proc'/str(p)/'maps','')
        file=r/'usr/bin'/role;write(file,'original '+role);baseline.append(sha(file)+'  '+file.as_posix())
    write(d/'baseline.sha256','\n'.join(baseline)+'\n')
    # 填足生产 manifest 的最低成员数，替身路径仍经真实摘要验证。
    for n in range(5):write(d/f'fixture-{n}',str(n))
    write(d/'manifest.sha256',''.join(sha(p)+'  '+p.relative_to(d).as_posix()+'\n' for p in sorted(d.rglob('*')) if p.is_file()))
    env=dict(os.environ, COMBINED_TEST_ROOT=str(r), COMBINED_TEST_PYTHON=sys.executable,
             COMBINED_TEST_FAKE=str(r/'fake.py'), COMBINED_TEST_BIN='/'+r.drive[0].lower()+(r/'bin').as_posix()[2:],
             MSYS_NO_PATHCONV='1', PYTHONDONTWRITEBYTECODE='1')
    return r,d,env

def run():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    OUT.mkdir(exist_ok=True,parents=True)
    parent=OUT / ('install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    parent.mkdir()
    for name in SOURCE_NAMES:subprocess.run([str(SHELL),'-n',str(HERE/name)],check=True,cwd=ROOT)
    checks=[]
    def call(d,e,phase):
        return subprocess.run([str(SHELL),'-c','PATH="$COMBINED_TEST_BIN:/usr/bin:/bin"; export PATH; exec sh "$@"','combined-test',str(d/'run.sh'),phase],
                              cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=60)
    def check(name, condition, result=None):
        if not condition:raise AssertionError((name,None if result is None else (result.returncode,result.stdout,result.stderr)))
        checks.append(name)
    def success(d,e,phase):
        result=call(d,e,phase);check(phase+' succeeds',result.returncode==0,result);return result
    def calls(r):return [json.loads(line) for line in (r/'calls.jsonl').read_text().splitlines()]
    r,d,e=fixture(parent,'normal')
    for phase in ('preflight','ui','observer','replay-prepare','replay-config','replay-jpeg','provider'):success(d,e,phase)
    records=calls(r)
    check('one immutable deadline',sum(v==['system-check','--begin-hold'] for v in records)==1)
    check('ordered owned service transitions',[v for v in records if v[0]=='systemctl' and v[1] in ('restart','stop','start')]==[
        ['systemctl','restart','victory-gui'],['systemctl','restart','msg2dbus-farm'],['systemctl','stop','victory-gui'],['systemctl','start','victory-gui']])
    result=call(d,e,'provider');check('duplicate refuses before services',result.returncode==62,result)
    write(d/'phases/unknown.sent','sent')
    result=call(d,e,'release');check('unknown phase blocks all later dispatch',result.returncode==62,result)
    r,d,e=fixture(parent,'expired');success(d,e,'ui');write(r/'expired','1')
    result=call(d,e,'observer');check('expired window prevents radio and farm',result.returncode==65 and not (r/'flash/formal-state/radio-prepared').exists(),result)
    r,d,e=fixture(parent,'changed-package');write(d/'af/libhbl-af-ui.so','changed')
    result=call(d,e,'ui');check('changed package refuses all installation',result.returncode==60 and not (d/'install-state').exists(),result)
    r,d,e=fixture(parent,'foreign-directory');(r/'af').mkdir()
    result=call(d,e,'ui');check('preexisting module directory preserved',result.returncode==61 and not (d/'install-state').exists(),result)
    r,d,e=fixture(parent,'provider-failure')
    for phase in ('ui','observer','replay-prepare','replay-config','replay-jpeg'):success(d,e,phase)
    write(r/'fail-provider','1');deadline=(d/'install-state/hold.deadline').read_bytes()
    result=call(d,e,'provider');check('provider failure records bounded exit',result.returncode==70 and (d/'phases/provider.exit').read_text().strip()=='70',result)
    success(d,e,'bridge')
    check('bridge recovery retains deadline',deadline==(d/'install-state/hold.deadline').read_bytes())
    success(d,e,'replay-restore')
    write(d/'install-state/ram.started','1')
    result=call(d,e,'restore-linux');check('RAM not verified prevents consumer stop',result.returncode==64,result)
    r,d,e=fixture(parent,'restore-before-ram');success(d,e,'ui');success(d,e,'observer')
    success(d,e,'restore-linux')
    check('restoration returns original services',all(v['active'] for v in json.loads((r/'services.json').read_text()).values()) and (d/'install-state/linux-restored.done').exists())
    r,d,e=fixture(parent,'foreign-dropin');success(d,e,'ui')
    target=r/'run/systemd/system/victory-gui.service.d/90-hbl-combined.conf';write(target,'foreign\n')
    result=call(d,e,'restore-linux');check('foreign dropin never removed',result.returncode==60 and target.read_text()=='foreign\n',result)
    proof={'passed':True,'checks':checks,'sources':{(HERE/name).relative_to(ROOT).as_posix():sha(HERE/name) for name in SOURCE_NAMES},
           'testSha256':sha(Path(__file__)),'hardwareRequests':0,'targetValidated':False,
           'boundaries':'实际 sh 与文件摘要；systemctl、UID/权限、socket 类型、原生硬件程序为隔离替身',
           'fixtureDirectory':parent.relative_to(ROOT).as_posix()}
    write(OUT/'install.json',json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0},ensure_ascii=False))

if __name__=='__main__':run()
