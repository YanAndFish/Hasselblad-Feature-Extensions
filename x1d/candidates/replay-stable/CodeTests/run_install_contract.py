"""执行安装/恢复脚本的工作副本；仅映射绝对路径，服务/进程/DBus 为明确替身。"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
OUT=HERE/'artifacts/install-tests'
SHELL=Path('C:/Program Files/Git/bin/sh.exe')
FILES=['common.sh','preflight.sh','install.sh','restore.sh','status.sh']
FAKE=r'''import json,os,sys,shlex
from pathlib import Path
r=Path(os.environ['REPLAY_TEST_ROOT']);d=r/'package';cmd=sys.argv[1];a=sys.argv[2:]
with (r/'commands.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps([cmd,*a])+'\n')
def write(p,s):
 p.parent.mkdir(parents=True,exist_ok=True)
 if isinstance(s,bytes):p.write_bytes(s)
 else:p.write_text(s,encoding='utf-8',newline='\n')
def flag(s):return (r/s).exists()
def drop(role):return r/'run/systemd/system'/(role+'.service.d')/'90-x1d-replay.conf'
def pid(role):return {'configstore':101,'storage-daemon':202,'jpeg-daemon':303,'victory-gui':404}[role]
def refresh(role):
 text=drop(role).read_text(encoding='utf-8') if drop(role).exists() else ''
 exe=r/'usr/bin'/role
 for line in text.splitlines():
  if line.startswith('ExecStart=') and line[10:]:exe=Path(line[10:])
 p=r/'proc'/str(pid(role));write(p/'exe',exe.read_bytes());write(p/'environ','')
 mapped=[]
 for line in text.splitlines():
  if line.startswith('Environment='):
   for entry in shlex.split(line[12:]):
    if entry.startswith('LD_PRELOAD='):mapped+=entry[11:].split()
 write(p/'maps','\n'.join(mapped)+'\n')
 if role=='victory-gui' and mapped:
  write(d/'state/ui',f'RPU1 {pid(role)} 1\n');write(d/'state/gpu',f'RPG1 {pid(role)} 100 8192 1 1\n')
if cmd=='id':print(0)
elif cmd=='stat':print('1000:700' if flag('bad-owner') else '0:700')
elif cmd=='sleep':pass
elif cmd=='systemctl':
 if a[0]=='daemon-reload':pass
 elif a[0]=='show':
  key=a[2];role=a[-1];path=drop(role)
  values={'LoadState':'loaded','ActiveState':'active','SubState':'running','MainPID':str(pid(role)),
          'FragmentPath':'/lib/systemd/system/'+role+'.service',
          'DropInPaths':str(path).replace('\\','/') if path.exists() else '',
          'Environment':'LD_PRELOAD=foreign.so' if flag('foreign-preload') else ''}
  if flag('inactive-'+role):values['ActiveState']='failed'
  if flag('foreign-fragment'):values['FragmentPath']='/etc/systemd/system/'+role+'.service'
  print(key+'='+values[key])
 elif a[0]=='restart':
  role=a[1];text=drop(role).read_text(encoding='utf-8') if drop(role).exists() else ''
  candidate=bool(text)
  if not candidate and flag('restore-failure'):sys.exit(1)
  fault='fail-'+role
  if candidate and flag(fault) and not flag(fault+'-used'):
   write(r/(fault+'-used'),'1');sys.exit(1)
  refresh(role)
 else:raise AssertionError(a)
elif cmd=='replay-check':
 if a[0]=='--begin':write(d/'state/deadline','RPD1 1200000\n')
 elif a[0]=='--owners':
  assert a[1:]==['101','303','202']
  if flag('owner-mismatch'):sys.exit(1)
 elif a[0] in ('--hold','--gpu'):
  if not drop('victory-gui').exists() or not (d/'state/deadline').exists():sys.exit(1)
  if flag('unhealthy') or (a[0]=='--gpu' and flag('bad-gpu')):sys.exit(1)
 elif a[0]=='--active' and flag('unhealthy'):sys.exit(1)
 elif a[0] not in ('--active','--selftest'):raise AssertionError(a)
 print('mock-check-pass')
else:raise AssertionError(cmd)
'''

def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(v,bytes):p.write_bytes(v)
    else:p.write_text(v,encoding='utf-8',newline='\n')

def fixture(name,flag=None):
    root=OUT/name
    if root.exists():
        target=root.resolve();target.relative_to(OUT.resolve());shutil.rmtree(target)
    root.mkdir(parents=True)
    d=root/'package';d.mkdir();(root/'run/systemd/system').mkdir(parents=True)
    write(root/'fake.py',FAKE)
    baseline=[]
    for role,pid in [('configstore',101),('storage-daemon',202),('jpeg-daemon',303),('victory-gui',404)]:
        b=('original-'+role).encode()
        write(root/'usr/bin'/role,b);write(root/'proc'/str(pid)/'exe',b)
        write(root/'proc'/str(pid)/'maps','');write(root/'proc'/str(pid)/'environ','')
        baseline.append(sha(b)+'  '+str(root/'usr/bin'/role).replace('\\','/'))
    for command in ('id','stat','systemctl','sleep','replay-check'):
        write((d if command=='replay-check' else root/'bin')/command,
              '#!/bin/sh\nexec "$REPLAY_TEST_PYTHON" "$REPLAY_TEST_FAKE" '+command+' "$@"\n')
    replacements={
        '/tmp/hbl-x1d-rp':str(d).replace('\\','/'),
        '/run/systemd/system':str(root/'run/systemd/system').replace('\\','/'),
        '/proc/':str(root/'proc').replace('\\','/')+'/',
        '/usr/bin/':str(root/'usr/bin').replace('\\','/')+'/',
        '/etc/ld.so.preload':str(root/'etc/ld.so.preload').replace('\\','/'),
    }
    for name in FILES:
        text=(HERE/'session'/name).read_text(encoding='utf-8')
        for old,new in replacements.items():text=text.replace(old,new)
        # 同一白名单在测试根目录下平移，未放宽 '..'/绝对路径校验。
        text=text.replace('^\\/(usr\\/bin|usr\\/lib|lib)\\/', '^'+str(root).replace('\\','/').replace('/','\\/')+'\\/(usr\\/bin|usr\\/lib|lib)\\/')
        write(d/name,text)
    for name in ['replay-ui.rcc','libx1d-replay-session.so','libx1d-replay-provider.so','libx1d-jpeg-adapter.so','payload/configstore','payload/jpeg-daemon']:
        write(d/name,('fixture-'+name).encode())
    write(d/'baseline.sha256','\n'.join(baseline)+'\n')
    payload=sorted(p for p in d.rglob('*') if p.is_file())
    write(d/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(d).as_posix()+'\n' for p in payload))
    if flag:write(root/flag,'1')
    env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+str(SHELL.parent)+os.pathsep+os.environ['PATH'],
             REPLAY_TEST_ROOT=str(root),REPLAY_TEST_PYTHON=sys.executable,REPLAY_TEST_FAKE=str(root/'fake.py'),
             REPLAY_TEST_BIN='/'+root.drive[0].lower()+(root/'bin').as_posix()[2:],
             MSYS_NO_PATHCONV='1',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    return root,d,env

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    for name in FILES:subprocess.run([str(SHELL),'-n',str(HERE/'session'/name)],check=True,cwd=ROOT)
    checks=[]
    def call(d,env,script,*args):return subprocess.run([str(SHELL),'-c','PATH="$REPLAY_TEST_BIN:/usr/bin:/bin"; export PATH; exec sh "$@"','replay-test',str(d/script),*args],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=100)
    def check(label,yes,detail=''):
        assert yes,(label,detail);checks.append(label)
    def mutations(r):
        records=[json.loads(s) for s in (r/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
        return [s for s in records if s[:2]==['systemctl','restart']]
    r,d,e=fixture('normal')
    result=call(d,e,'preflight.sh');check('preflight-no-service-mutation',result.returncode==0 and not mutations(r),result.stdout+result.stderr)
    result=call(d,e,'install.sh','--stage-ui');check('ui-first',result.returncode==0 and (d/'state/ui-ready').exists(),result.stdout+result.stderr)
    check('ui-stage-only-restarts-gui',mutations(r)==[['systemctl','restart','victory-gui']])
    result=call(d,e,'install.sh','--enable');check('enable',result.returncode==0 and (d/'state/enabled').exists() and (d/'state/release').exists(),result.stdout+result.stderr)
    check('dependency-order',mutations(r)==[['systemctl','restart',n] for n in ['victory-gui','configstore','jpeg-daemon','victory-gui']])
    maps=(r/'proc/404/maps').read_text();check('both-preloads-quoted-correctly','libx1d-replay-session.so' in maps and 'libx1d-replay-provider.so' in maps)
    result=call(d,e,'status.sh');check('live-status-bounded',result.returncode==0 and len(result.stdout.encode())<160 and 'live-health=active' in result.stdout and 'live-services=match' in result.stdout,result.stdout+result.stderr)
    result=call(d,e,'restore.sh');check('restore-success',result.returncode==0 and (d/'state/restored').exists(),result.stdout+result.stderr)
    before=mutations(r);result=call(d,e,'restore.sh');check('restore-repeat-no-restart',result.returncode==0 and mutations(r)==before)
    for flag in ['bad-owner','foreign-preload','foreign-fragment','owner-mismatch','unhealthy','inactive-configstore']:
        r,d,e=fixture(flag,flag);result=call(d,e,'install.sh','--stage-ui')
        check(flag+'-precondition-refused',result.returncode!=0 and not (d/'state').exists() and not mutations(r),result.stdout+result.stderr)
    r,d,e=fixture('corrupt');write(d/'replay-ui.rcc','corrupt')
    result=call(d,e,'install.sh','--stage-ui');check('corrupt-package-no-mutation',result.returncode!=0 and not (d/'state').exists())
    r,d,e=fixture('bad-gpu','bad-gpu');result=call(d,e,'install.sh','--stage-ui')
    check('bad-gpu-restores-gui',result.returncode!=0 and (d/'state/restored').exists() and not (d/'state/enabled').exists(),result.stdout+result.stderr)
    for role in ['configstore','jpeg-daemon']:
        r,d,e=fixture('fail-'+role,'fail-'+role)
        result=call(d,e,'install.sh','--stage-ui');check(role+'-ui-ready',result.returncode==0,result.stdout+result.stderr)
        result=call(d,e,'install.sh','--enable');check(role+'-failure-restored',result.returncode!=0 and (d/'state/restored').exists(),result.stdout+result.stderr)
    r,d,e=fixture('ui-failure','fail-victory-gui');result=call(d,e,'install.sh','--stage-ui')
    check('first-ui-failure-restored',result.returncode!=0 and (d/'state/restored').exists(),result.stdout+result.stderr)
    r,d,e=fixture('full-ui-failure');result=call(d,e,'install.sh','--stage-ui');assert result.returncode==0
    write(r/'fail-victory-gui','1');result=call(d,e,'install.sh','--enable')
    check('final-ui-failure-restores-all',result.returncode!=0 and (d/'state/restored').exists(),result.stdout+result.stderr)
    r,d,e=fixture('restore-failure','bad-gpu');write(r/'restore-failure','1')
    result=call(d,e,'install.sh','--stage-ui')
    check('failed-restore-never-marked-complete',result.returncode!=0 and not (d/'state/restored').exists() and 'replay-rollback-incomplete' in result.stdout,result.stdout+result.stderr)
    r,d,e=fixture('foreign-drop');result=call(d,e,'install.sh','--stage-ui');assert result.returncode==0
    drop=r/'run/systemd/system/victory-gui.service.d/90-x1d-replay.conf';write(drop,'foreign-content\n')
    result=call(d,e,'restore.sh');check('foreign-drop-retained',result.returncode==73 and drop.read_text()=='foreign-content\n')
    r,d,e=fixture('missing-stage');result=call(d,e,'install.sh','--enable')
    check('enable-without-ui-refused',result.returncode!=0 and not mutations(r))
    report={'passed':True,'checks':checks,'checkCount':len(checks),'cameraAccess':False,'realServices':False,
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),*[HERE/'session'/n for n in FILES]]}}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'installerChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
