"""组合后端的实际 shell 工作副本：服务/DBus/共同窗口为替身，禁止触及受保护模块。"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from run_install_contract import FAKE as BASE_FAKE,write
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
OUT=HERE/'artifacts/joint-backend-tests';SHELL='C:/Program Files/Git/bin/sh.exe'
PIDS={'configstore':101,'storage-daemon':202,'jpeg-daemon':303,'victory-gui':404,'msg2dbus-farm':505}

def sha(data):return hashlib.sha256(data).hexdigest()
FAKE=BASE_FAKE.replace("d=r/'package'","d=r/'combined/replay'")
FAKE=FAKE.replace("{'configstore':101,'storage-daemon':202,'jpeg-daemon':303,'victory-gui':404}",repr(PIDS))
FAKE=FAKE.replace("'90-x1d-replay.conf'","'90-x1d-replay-joint.conf'")
FAKE=FAKE.replace("elif cmd=='stat':print('1000:700' if flag('bad-owner') else '0:700')",'''elif cmd=='stat':
 if a[1]=='%u:%h':print('0:1')
 elif a[1]=='%s':print(Path(a[2]).stat().st_size)
 else:print('1000:700' if flag('bad-owner') else '0:700')''')
FAKE=FAKE.replace("elif cmd=='replay-check':",'''elif cmd=='system-check':
 assert a==['--require-held-min-ms','90000']
 if flag('expired-hold'):sys.exit(1)
elif cmd=='replay-joint-check':
 assert a==['--gpu','404']
 if flag('bad-gpu'):sys.exit(1)
elif cmd=='replay-check':''')

def fixture(name,flag=None):
    r=OUT/name
    if r.exists():r.resolve().relative_to(OUT.resolve());shutil.rmtree(r)
    d=r/'combined/replay';d.mkdir(parents=True);(r/'combined/replay-state').mkdir();(r/'run/systemd/system').mkdir(parents=True)
    write(r/'fake.py',FAKE)
    write(r/'wireless-flash/formal-worker.status','formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=505\n')
    for cmd in ('id','stat','systemctl','sleep','system-check','replay-joint-check','replay-check'):
        target=r/'bin'/cmd
        if cmd=='system-check':target=r/'combined/system-check'
        if cmd=='replay-joint-check':target=d/cmd
        if cmd=='replay-check':target=d/'replay-owners'
        write(target,'#!/bin/sh\nexec "$REPLAY_TEST_PYTHON" "$REPLAY_TEST_FAKE" '+cmd+' "$@"\n')
    baseline=[]
    for role,pid in PIDS.items():
        b=('original-'+role).encode();write(r/'usr/bin'/role,b);write(r/'proc'/str(pid)/'exe',b)
        write(r/'proc'/str(pid)/'maps','');write(r/'proc'/str(pid)/'environ','')
        write(r/'proc'/str(pid)/'stat',str(pid)+' ('+role+') S '+' '.join(['0']*18)+' '+str(1000+pid)+'\n')
        baseline.append(sha(b)+'  '+(r/'usr/bin'/role).as_posix())
    write(d/'baseline.sha256','\n'.join(baseline)+'\n')
    write(d/'coordinator.sha256',sha((r/'combined/system-check').read_bytes())+'  '+(r/'combined/system-check').as_posix()+'\n')
    for name in ('libx1d-replay-joint.so','libx1d-replay-provider.so','libx1d-jpeg-adapter.so','payload/configstore','payload/jpeg-daemon'):
        write(d/name,('fixture-'+name).encode())
    source=(HERE/'joint/backend.sh').read_text(encoding='utf-8')
    for old,new in {'/tmp/hbl-x1d-combined':(r/'combined').as_posix(),'/tmp/hbl-wireless-flash':(r/'wireless-flash').as_posix(),'/run/systemd/system':(r/'run/systemd/system').as_posix(),
                    '/proc/':(r/'proc').as_posix()+'/', '/usr/bin/':(r/'usr/bin').as_posix()+'/',
                    '/etc/ld.so.preload':(r/'etc/ld.so.preload').as_posix()}.items():source=source.replace(old,new)
    write(d/'backend.sh',source)
    write(d/'manifest.sha256',''.join(sha(p.read_bytes())+'  '+p.relative_to(d).as_posix()+'\n' for p in sorted(d.rglob('*')) if p.is_file()))
    if flag:write(r/flag,'1')
    env=dict(os.environ,REPLAY_TEST_ROOT=str(r),REPLAY_TEST_PYTHON=sys.executable,REPLAY_TEST_FAKE=str(r/'fake.py'),
             REPLAY_TEST_BIN='/'+r.drive[0].lower()+(r/'bin').as_posix()[2:],MSYS_NO_PATHCONV='1',PYTHONDONTWRITEBYTECODE='1')
    return r,d,env

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    subprocess.run([SHELL,'-n',str(HERE/'joint/backend.sh')],check=True,cwd=ROOT)
    checks=[]
    def call(d,e,phase):return subprocess.run([SHELL,'-c','PATH="$REPLAY_TEST_BIN:/usr/bin:/bin"; export PATH; exec sh "$@"','joint-test',str(d/'backend.sh'),phase],
                                             cwd=ROOT,env=e,capture_output=True,text=True,encoding='utf-8',timeout=100)
    def check(label,result,ok):assert ok,(label,result.stdout,result.stderr);checks.append(label)
    def restarts(r):
        records=[json.loads(s) for s in (r/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
        return [a for a in records if a[:2]==['systemctl','restart']]
    r,d,e=fixture('normal');s=r/'combined/replay-state/backend'
    for phase in ('--prepare','--config','--jpeg'):
        result=call(d,e,phase);check(phase+'-succeeds',result,result.returncode==0)
    result=call(d,e,'--status');check('bounded-status',result,result.returncode==0 and len(result.stdout)<200 and 'protected-processes=match' in result.stdout and 'config=candidate jpeg=candidate' in result.stdout)
    check('only-ordered-backend-restarts',result,restarts(r)==[['systemctl','restart','configstore'],['systemctl','restart','jpeg-daemon']])
    result=call(d,e,'--jpeg');check('duplicate-stage-rejected',result,result.returncode==64)
    result=call(d,e,'--restore');check('restore-backend-only',result,result.returncode==0 and (s/'restore.done').exists() and
                                     restarts(r)==[['systemctl','restart',n] for n in ('configstore','jpeg-daemon','configstore','jpeg-daemon')])
    before=restarts(r);result=call(d,e,'--restore');check('no-blind-second-restore',result,result.returncode==64 and restarts(r)==before)
    commands=[json.loads(line) for line in (r/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
    check('no-independent-worker-service-assumed',result,not any('hbl-wireless-worker' in entry for entry in commands))
    for role in ('configstore','jpeg-daemon'):
        r,d,e=fixture('fail-'+role,'fail-'+role);s=r/'combined/replay-state/backend'
        result=call(d,e,'--prepare');assert result.returncode==0,result.stdout+result.stderr
        if role=='jpeg-daemon':assert call(d,e,'--config').returncode==0
        result=call(d,e,'--config' if role=='configstore' else '--jpeg')
        check(role+'-failure-stops-without-global-rollback',result,result.returncode==66 and not (s/'restore.sent').exists())
        result=call(d,e,'--restore');check(role+'-explicit-backend-restore',result,result.returncode==0 and (s/'restore.done').exists())
    for flag in ('expired-hold','bad-gpu','owner-mismatch'):
        r,d,e=fixture(flag,flag);result=call(d,e,'--prepare')
        check(flag+'-before-mutation',result,result.returncode==63 and not restarts(r) and not (r/'combined/replay-state/backend').exists())
    valid='formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=505\n'
    for label,content in [
        ('worker-other-process',valid.replace('same-process=1','same-process=0')),
        ('worker-wrong-pid',valid.replace('pid=505','pid=506')),
        ('worker-master-on',valid.replace('master=0','master=1')),
        ('worker-radio-held',valid.replace('radio-held=0','radio-held=1')),
        ('worker-radio-busy',valid.replace('radio-busy=0','radio-busy=1')),
        ('worker-stopped',valid.replace('ready-default-off','stopped-default-off')),
        ('worker-extra-field',valid.rstrip()+' extra=1\n'),
    ]:
        r,d,e=fixture(label);write(r/'wireless-flash/formal-worker.status',content)
        result=call(d,e,'--prepare');check(label+'-refused-before-mutation',result,result.returncode==63 and not restarts(r))
    r,d,e=fixture('worker-disappeared');assert call(d,e,'--prepare').returncode==0
    (r/'wireless-flash/formal-worker.status').unlink()
    result=call(d,e,'--config');check('worker-disappeared-after-prepare-stops',result,result.returncode==63 and not restarts(r))
    r,d,e=fixture('protected-changed');assert call(d,e,'--prepare').returncode==0
    write(r/'proc/505/stat','505 (changed) S '+' '.join(['0']*18)+' 9999\n')
    result=call(d,e,'--config');check('protected-process-change-stops',result,result.returncode==63 and not restarts(r))
    r,d,e=fixture('pending');assert call(d,e,'--prepare').returncode==0
    write(r/'combined/replay-state/backend/config.sent','')
    result=call(d,e,'--restore');check('pending-phase-forbids-restore',result,result.returncode==64 and not restarts(r))
    r,d,e=fixture('unknown-drop');assert call(d,e,'--prepare').returncode==0;assert call(d,e,'--config').returncode==0
    path=r/'run/systemd/system/configstore.service.d/90-x1d-replay-joint.conf';write(path,'foreign\n');before=restarts(r)
    result=call(d,e,'--restore');check('foreign-drop-retained',result,result.returncode==65 and path.read_text()=='foreign\n' and restarts(r)==before)
    r,d,e=fixture('recovery-fails');assert call(d,e,'--prepare').returncode==0;assert call(d,e,'--config').returncode==0
    write(r/'restore-failure','1');result=call(d,e,'--restore')
    check('failed-recovery-not-complete',result,result.returncode==66 and not (r/'combined/replay-state/backend/restore.done').exists())
    report={'passed':True,'checks':checks,'checkCount':len(checks),'cameraAccess':False,'realServices':False,
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'joint/backend.sh',HERE/'CodeTests/run_install_contract.py']}}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'jointBackendChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
