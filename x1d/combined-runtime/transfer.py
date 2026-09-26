"""固定组合包的有界串行传输；导入与默认运行均离线。"""
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import shlex
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/research'))
from mechanical_sync_session import Session as OriginalSession
from mechanical_hw_ready_transfer import DECODER
import build_package

REMOTE='/tmp/hbl-x1d-combined'
PHASES=('preflight','ui','observer','provider','bridge','enable','release',
        'replay-prepare','replay-config','replay-jpeg','replay-restore','worker-stop','restore-linux')

class Session:
    """每64个请求独立一份原格式日志；避免大包逐帧重写数千条旧记录。"""
    def __init__(self,name):
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):raise ValueError('session name')
        self.directory=HERE/'build/sessions'/(name+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.directory.mkdir(parents=True,exist_ok=False)
        self.sessions=[];self.failed=False;self.dispatched=set()
    @property
    def entries(self):return [entry for session in self.sessions for entry in session.entries]
    def command(self,label,command,timeout_ms=15000):
        if self.failed:raise RuntimeError('session stopped')
        if not self.sessions or len(self.sessions[-1].entries)>=64:
            session=OriginalSession(self.directory.name+'-'+str(len(self.sessions))+'.json')
            session.output=self.directory/(str(len(self.sessions)).zfill(4)+'.json')
            self.sessions.append(session)
        try:return self.sessions[-1].command(label,command,timeout_ms)
        except BaseException:
            self.failed=True
            raise
    def summary(self):
        entries=self.entries
        return {'directory':self.directory.relative_to(ROOT).as_posix(),'requests':sum(e['submitted'] for e in entries),
                'allHandlesClosed':all(e['closed'] for e in entries),'failed':self.failed,'dispatched':sorted(self.dispatched)}

def stage(session,report,data,pause=time.sleep):
    if hashlib.sha256(data).hexdigest()!=report['packageSha256'] or len(data)!=report['bytes']:raise ValueError('package identity before USB')
    result=session.command('services','systemctl is-active victory-gui msg2dbus-farm storage-daemon configstore jpeg-daemon')
    if result['output'].split()!=['active']*5:raise RuntimeError('camera services not ready')
    session.command('create-stage','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r" "$r/phases"')
    for index,start in enumerate(range(0,len(DECODER),90)):
        session.command('decoder-'+str(index),'printf %s '+shlex.quote(DECODER[start:start+90])+(' >' if index==0 else ' >>')+REMOTE+'/d.awk')
    encoded=base64.b64encode(data).decode('ascii')
    parts=[encoded[n:n+176] for n in range(0,len(encoded),176)]
    for index,part in enumerate(parts):
        session.command('chunk-'+str(index),'printf %s '+shlex.quote(part)+(' >' if index==0 else ' >>')+REMOTE+'/p64')
        if (index+1)%100==0:print(json.dumps({'stage':'transfer','chunks':index+1,'total':len(parts)}),flush=True)
    session.command('decode-once','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/combined.tar.gz";sha256sum "$r/combined.tar.gz" >"$r/decode.sha") </dev/null >/dev/null 2>&1 &')
    for attempt in range(120):
        pause(1)
        result=session.command('decode-observe-'+str(attempt),'r='+REMOTE+';if test -f "$r/decode.sha";then cat "$r/decode.sha";else printf pending;fi')
        if result['output']!='pending':break
    else:raise RuntimeError('decode outcome pending; do not repeat')
    if result['output'].split()[0]!=report['packageSha256']:raise RuntimeError('archive mismatch; extraction refused')
    result=session.command('extract-once','cd '+REMOTE+' && tar xzf combined.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf combined-package-verified')
    if result['output']!='combined-package-verified':raise RuntimeError('extraction verification failed')
    return {'staged':True,'chunks':len(parts),'packageSha256':report['packageSha256']}

def start(session,phase):
    if phase not in PHASES or phase in session.dispatched:raise ValueError('phase unknown or already dispatched')
    session.dispatched.add(phase)
    session.command(phase+'-once','r='+REMOTE+';p='+phase+';test ! -e "$r/phases/$p.sent" && (sh "$r/run.sh" "$p" >"$r/phases/$p.log" 2>&1) </dev/null >/dev/null 2>&1 &')

def poll(session,phase):
    if phase not in PHASES:raise ValueError('unknown phase')
    result=session.command(phase+'-observe','r='+REMOTE+';p='+phase+';if test -f "$r/phases/$p.exit";then cat "$r/phases/$p.exit";tail -n 1 "$r/phases/$p.log";else printf pending;fi')
    return result['output'].strip()

def validate():
    data=b'bounded-archive-model'*100
    report={'packageSha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    class Model:
        def __init__(self,failure=None):self.calls=[];self.failure=failure;self.failed=False;self.dispatched=set()
        def command(self,label,command,timeout_ms=15000):
            if self.failed:raise AssertionError('reused failed session')
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command and '\x00' not in command
            self.calls.append((label,command))
            if label=='chunk-3' and self.failure=='unknown':self.failed=True;raise RuntimeError('synthetic ambiguous write')
            if label=='services':out='\n'.join(['active']*5)
            elif label.startswith('decode-observe'):out=('0'*64 if self.failure=='hash' else report['packageSha256'])+'  archive'
            elif label=='extract-once':out='combined-package-verified'
            elif label.endswith('-observe'):out='pending'
            else:out=''
            return {'output':out,'closed':True,'exit_code':0}
    checks=[]
    model=Model();stage(model,report,data,lambda _:None);checks.append('full bounded ordered transfer')
    for phase in PHASES:start(model,phase);poll(model,phase)
    checks.append('all phase requests fit reviewed frame')
    before=len(model.calls)
    try:start(model,'ui')
    except ValueError:pass
    else:raise AssertionError('phase replay accepted')
    assert len(model.calls)==before;checks.append('no duplicate phase request')
    for failure in ('unknown','hash'):
        model=Model(failure)
        try:stage(model,report,data,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError('failure not propagated')
        assert not any(label=='extract-once' for label,_ in model.calls)
        if failure=='unknown':assert model.calls[-1][0]=='chunk-3'
        checks.append(failure+' stops without extraction or retry')
    proof={'passed':True,'checks':checks,'sources':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
           (Path(__file__),ROOT/'x1d/wireless-flash/research/mechanical_sync_session.py',ROOT/'x1d/wireless-flash/research/mechanical_hw_ready_transfer.py')},'hardwareRequests':0}
    target=HERE/'CodeTests/output/transfer.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))

if __name__=='__main__':validate()
