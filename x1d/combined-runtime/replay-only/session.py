"""主任务独占执行现成独立回放包；默认离线，设备动作必须显式选择。"""
from pathlib import Path
from datetime import datetime, timezone
import base64, hashlib, json, os, shlex, subprocess, sys, time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import transfer as root_transfer
sys.path.insert(0, str(ROOT/'x1d/candidates/replay-next/tools'))
from transfer_session import Transfer, REMOTE, verify_package, DECODER

# 用户实测连续放大黑屏并停在开机标志。仅脚本派生均使用同一功能二进制，禁止重装。
REJECTED_FUNCTIONAL_PACKAGES={
    '4ff2a1981ecf52546b0f743ea6eb6622a8aceac8db968c03262496a44c439a78',
    '4f0972bd1dfee7bae72885d0cdf94895cdce1dd1ca714a52441ae6a1c2297a50',
    '52097c8876eda1c1f87215b43fc241f65893f3ef6742aeca8fab86b3617cefd6',
    'cd11f9988b86d5018ea02f92819b34a1b7e0568b234f696f2e7cf29f63162108',
}
def require_repaired_package(report):
    if report['packageSha256'] in REJECTED_FUNCTIONAL_PACKAGES:
        raise RuntimeError('Current replay binary failed multi-image zoom; a repaired delivery is required before hardware access')

HELPER = ';'.join([
    'set -eu', 'r='+REMOTE,
    '''trap 'result=$?;echo "$result" >"$r/decode.exit"' 0''',
    'test ! -e "$r/session.tar.gz"',
    '''printf '%b' "$(/usr/bin/od -v -c "$r/p64" | /bin/sed 's/^[0-7]* *//' | awk -f "$r/d.awk")" >"$r/session.tar.gz"''',
    'sha256sum "$r/session.tar.gz" >"$r/decode.sha"',
])

class StreamingTransfer(Transfer):
    def upload(self, progress=None):
        if self.staged or self.decodeSent: raise RuntimeError('Upload already sent')
        self.send('replay-create', f'umask 077;test ! -e {REMOTE} && test ! -L {REMOTE} && mkdir -m 700 {REMOTE}')
        for name, body in [('d.awk', DECODER), ('decode.sh', HELPER)]:
            for i, start in enumerate(range(0, len(body), 70)):
                self.send(name+'-'+str(i), 'printf %s '+shlex.quote(body[start:start+70])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        got=self.send('helper-hash', 'sha256sum '+REMOTE+'/decode.sh')
        if got.split()[0] != hashlib.sha256(HELPER.encode()).hexdigest(): raise RuntimeError('Helper changed')
        encoded=base64.b64encode(self.data).decode('ascii')
        parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
        for i,part in enumerate(parts):
            self.send('replay-chunk-'+str(i),'printf %s '+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if progress and (i+1)%100==0: progress(i+1,len(parts))
        self.decodeSent=True
        self.send('replay-decode',f'r={REMOTE};(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        return {'decodeDispatched':True,'chunks':len(parts)}
    def finish_upload(self):
        if not self.decodeSent or self.staged: raise RuntimeError('No pending upload')
        out=self.send('replay-decode-result',f'r={REMOTE};if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi')
        if out=='pending': return False
        if out.split()[:2]!=['0',self.report['packageSha256']]:
            self.stopped=True
            raise RuntimeError('Decode failed or archive differs; extraction refused')
        out=self.send('replay-extract',f'cd {REMOTE} && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf replay-package-verified')
        if out!='replay-package-verified': raise RuntimeError('Extraction not verified')
        self.staged=True
        return True

def save(session, state, name):
    state.update(session.summary())
    (session.directory/name).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def stage():
    report,data=verify_package()
    require_repaired_package(report)
    session=root_transfer.Session('replay-only-stage')
    state={'staged':False,'packageSha256':report['packageSha256'],'packageBytes':len(data),'farmRequests':0}
    t=StreamingTransfer(session,(report,data))
    try:
        out=t.send('original-services','systemctl is-active victory-gui msg2dbus-farm storage-daemon configstore jpeg-daemon')
        if out.split()!=['active']*5: raise RuntimeError('Original services not active')
        t.send('fresh-boot-stage', 'test ! -e /tmp/hbl-x1d-combined && test ! -L /tmp/hbl-x1d-combined')
        for role in ('victory-gui','configstore','jpeg-daemon'):
            out=t.send('original-dropins-'+role, 'systemctl show -p DropInPaths '+role)
            if out!='DropInPaths=': raise RuntimeError('Existing service modification')
        print(json.dumps({'stage':'original-services-ready','packageBytes':len(data)}),flush=True)
        t.upload(lambda done,total:print(json.dumps({'stage':'replay-transfer','chunks':done,'total':total}),flush=True))
        for _ in range(120):
            time.sleep(1)
            if t.finish_upload(): break
        else: raise RuntimeError('Decode pending; no retry')
        state['staged']=True
    except BaseException as e:
        state['failure']=str(e)
        raise
    finally:
        save(session,state,'stage.json')
        print(json.dumps(state),flush=True)
    return session.directory/'stage.json'

def install(evidence):
    report,data=verify_package()
    require_repaired_package(report)
    evidence=Path(evidence).resolve()
    if not evidence.is_relative_to(HERE.parent/'build/sessions') or evidence.name!='stage.json': raise ValueError('Evidence path')
    prior=json.loads(evidence.read_text(encoding='utf-8'))
    if not prior.get('staged') or prior.get('failed') or not prior.get('allHandlesClosed') or prior.get('packageSha256')!=report['packageSha256']: raise ValueError('Incomplete staging')
    session=root_transfer.Session('replay-only-install')
    state={'completed':False,'packageSha256':report['packageSha256'],'stageEvidence':evidence.relative_to(ROOT).as_posix(),
           'afInstalled':False,'flashInstalled':False,'residentUiInstalled':False,'shots':0,'photoReads':0,'farmRequests':0}
    t=StreamingTransfer(session,(report,data));t.staged=True
    try:
        got=t.send('staged-manifest-hash','sha256sum '+REMOTE+'/manifest.sha256')
        if got.split()[0]!=report['files']['manifest.sha256']: raise RuntimeError('Staged package changed')
        for phase in ('ui','enable'):
            state['stage']=phase+'-dispatch-intent';save(session,state,'installation.json')
            session.dispatched.add(phase)
            t.dispatch(phase)
            for _ in range(120):
                time.sleep(1)
                result=t.result(phase)
                if not result['pending']: break
            else: raise RuntimeError('Phase pending; no repeat')
            state[phase+'Result']=result;save(session,state,'installation.json')
            if result['exit_code']!=0: raise RuntimeError('Phase failed: '+result['detail'])
            state['stage']=phase+'-verified';save(session,state,'installation.json')
            print(json.dumps({'stage':state['stage'],'detail':result['detail']}),flush=True)
        state['liveStatus']=t.send('live-status','sh '+REMOTE+'/status.sh')
        if state['liveStatus']!='replay-status recorded=enabled live-health=active live-services=match':
            raise RuntimeError('Loaded package live state not confirmed')
        state['completed']=True;state['stage']='replay-only-loaded-awaiting-user-validation'
    except BaseException as e:
        state['failure']=str(e)
        raise
    finally:
        save(session,state,'installation.json')
        print(json.dumps(state),flush=True)

def validate():
    report,data=verify_package()
    out=HERE/'CodeTests'/('transfer-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True,exist_ok=False)
    class Model:
        failed=False
        def __init__(self): self.commands=[]
        def command(self,label,command):
            self.commands.append(command)
            response=hashlib.sha256(HELPER.encode()).hexdigest()+' helper' if label=='helper-hash' else ''
            return {'exit_code':0,'closed':True,'output':response}
    model=Model();t=StreamingTransfer(model,(report,data));t.upload()
    dest=(out/'staged').as_posix()
    lines=['set -eu','PATH=/usr/bin:/bin; export PATH']+[c.replace(REMOTE,dest).replace('mkdir -m 700','mkdir') for c in model.commands]
    lines+=['wait','cd "'+dest+'"','test "$(cat decode.exit)" = 0','sha256sum -c decode.sha','tar xzf session.tar.gz','sha256sum -c manifest.sha256']
    script=out/'transfer.sh';script.write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe',str(script)],cwd=ROOT,env=dict(os.environ,MSYS_NO_PATHCONV='1'),capture_output=True,text=True,timeout=120)
    if result.returncode: raise RuntimeError(result.stdout+result.stderr)
    assert (out/'staged/session.tar.gz').read_bytes()==data
    for name,wanted in report['files'].items(): assert hashlib.sha256((out/'staged'/name).read_bytes()).hexdigest()==wanted
    t.staged=True
    for phase in ('ui','enable','restore'):
        t.dispatch(phase);t.completed[phase]=0
    checks={'passed':True,'realShellStreamDecodeAndExtract':True,'members':len(report['files']),'maxCommandBytes':max(map(len,model.commands)),
            'packageSha256':report['packageSha256'],'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cameraRequests':0}
    (out/'validation.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(checks),flush=True)

if __name__=='__main__':
    if sys.argv[1:]==['--stage']: stage()
    elif len(sys.argv)==3 and sys.argv[1]=='--install-staged': install(sys.argv[2])
    elif sys.argv[1:]==['--validate']: validate()
    elif not sys.argv[1:]:
        r,d=verify_package();print(json.dumps({'verified':True,'bytes':len(d),'cameraRequests':0,
            'blockedByZoomFailure':r['packageSha256'] in REJECTED_FUNCTIONAL_PACKAGES}))
    else: raise SystemExit('No action')
