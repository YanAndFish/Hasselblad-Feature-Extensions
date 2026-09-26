"""保留原归档，修正 baseline 路径中原厂 libstdc++ 的合法字符。"""
from pathlib import Path
import base64, gzip, hashlib, io, json, re, shlex, subprocess, sys, tarfile
sys.dont_write_bytecode=True
import session as runner
HERE=Path(__file__).resolve().parent
OUT=HERE/'build/baseline-plus-r2'
ORIGINAL_VERIFY=runner.verify_package
FIX_SHARED_MAPS=False
PREVIOUS_PHASE='ui'
NEXT_PHASE='ui-r2'
PRIOR_FOLDER='baseline-plus-r2'
MAP_CHECK='index($0,"(deleted)") && !($2=="rw-s" && NF==7 && $7=="(deleted)" && ($6=="/dev/zero" || (index($6,"/tmp/weston-shared-")==1 && substr($6,20)~/^[A-Za-z0-9]+$/))) {bad=1} END {exit bad}'

def digest(data): return hashlib.sha256(data).hexdigest()

def build():
    original,data=ORIGINAL_VERIFY()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        files={m.name:archive.extractfile(m).read() for m in archive}
    before=files['common.sh'].decode()
    head,tail=before.split('baseline_check() {',1)
    old='[A-Za-z0-9_.\\/-]';new='[A-Za-z0-9_.+\\/-]'
    assert tail.count(old)==1
    after=head+'baseline_check() {'+tail.replace(old,new,1)
    assert before.replace(old,new,1)!=after  # 不误改前面的包成员规则。
    program=re.search(r"awk '([^']+)'", after.split('baseline_check() {',1)[1]).group(1)
    awk='C:/Program Files/Git/usr/bin/awk.exe'
    def accepts(value):
        return subprocess.run([awk,program],input=value,capture_output=True).returncode==0
    baseline=files['baseline.sha256']
    assert len(baseline.splitlines())==74 and accepts(baseline)
    invalid=[b'0'*64+b'  /tmp/foreign\n',b'0'*64+b'  /usr/lib/../foreign\n',
             b'0'*64+b'  /usr/lib/bad file\n',b'0'*63+b'  /usr/lib/x\n',baseline+baseline.splitlines()[0]+b'\n']
    assert all(not accepts(v) for v in invalid)
    if FIX_SHARED_MAPS:
        old_maps='! grep -q \'(deleted)\' "/proc/$p/maps"'
        assert after.count(old_maps)==1
        after=after.replace(old_maps,"awk '"+MAP_CHECK+"' \"/proc/$p/maps\"",1)
        def maps_ok(value):
            return subprocess.run([awk,MAP_CHECK],input=value.encode(),capture_output=True).returncode==0
        base='00000000-00001000 rw-s 00000000 00:05 1 /dev/zero (deleted)\n'
        assert maps_ok(base)
        assert maps_ok(base.replace('/dev/zero','/tmp/weston-shared-Abc123'))
        assert maps_ok('00000000-00001000 r-xp 00000000 08:01 2 /usr/lib/libQt5Core.so.5\n')
        for value in (base.replace('rw-s','r-xs'),base.replace('rw-s','rw-p'),base.replace('/dev/zero','/tmp/foreign.so'),base.replace('(deleted)','(deleted) extra')):
            assert not maps_ok(value)
    files['common.sh']=after.encode()
    files['manifest.sha256']=''.join(digest(value)+'  '+name+'\n' for name,value in sorted(files.items()) if name!='manifest.sha256').encode()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,value in sorted(files.items()):
            m=tarfile.TarInfo(name);m.size=len(value);m.mode=0o700;m.uid=m.gid=m.mtime=0
            archive.addfile(m,io.BytesIO(value))
    derived=gzip.compress(raw.getvalue(),mtime=0)
    report={**original,'packageSha256':digest(derived),'packageBytes':len(derived),
            'files':{name:digest(value) for name,value in files.items()},'baseArchiveSha256':original['packageSha256'],
            'deltaOnly':['common.sh','manifest.sha256'],'baselinePathsPassed':74,'invalidInputsRejected':len(invalid),
            'sharedBufferMapFix':FIX_SHARED_MAPS,'sharedMapChecks':7 if FIX_SHARED_MAPS else 0}
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ('common.sh','manifest.sha256'): (OUT/name).write_bytes(files[name])
    (OUT/'session.tar.gz').write_bytes(derived)
    (OUT/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/'validation.json').write_text(json.dumps({'passed':True,'originalArchiveUnchanged':True,'baselinePaths':74,
        'negativeChecks':len(invalid),'allElfAndRccBytesUnchanged':True,'cameraRequests':0,
        'sourceSha256':digest(Path(__file__).read_bytes())},indent=2)+'\n')
    return report,derived

def verify_delta():
    r=json.loads((OUT/'package.json').read_text())
    data=(OUT/'session.tar.gz').read_bytes()
    assert digest(data)==r['packageSha256']
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        seen=set()
        for m in archive:
            assert m.isfile() and m.name in r['files'] and m.name not in seen
            assert digest(archive.extractfile(m).read())==r['files'][m.name]
            seen.add(m.name)
        assert seen==set(r['files'])
    return r,data

def stage_delta():
    r,_=verify_delta();old,_=ORIGINAL_VERIFY()
    runner.require_repaired_package(r)
    if FIX_SHARED_MAPS: old=json.loads((HERE/'build'/PRIOR_FOLDER/'package.json').read_text())
    s=runner.root_transfer.Session('replay-only-baseline-delta')
    state={'staged':False,'packageSha256':r['packageSha256'],'baseArchiveSha256':r['baseArchiveSha256'],
           'predecessorPackageSha256':old['packageSha256'],
           'archiveRetransmitted':False,'deltaOnly':r['deltaOnly'],'farmRequests':0}
    t=runner.StreamingTransfer(s)
    d=runner.REMOTE
    try:
        out=t.send('ended-preflight-only',f'r={d};test "$(cat "$r/{PREVIOUS_PHASE}.exit")" = 64 && test ! -e "$r/state" && test ! -e "$r/enable.sent" && printf ended-before-services')
        assert out=='ended-before-services'
        out=t.send('original-manifest',f'sha256sum {d}/manifest.sha256')
        assert out.split()[0]==old['files']['manifest.sha256']
        t.send('original-file-set',f'cd {d} && sha256sum -c manifest.sha256 >/dev/null')
        for name in ('common.sh','manifest.sha256'):
            content=(OUT/name).read_bytes();encoded=base64.b64encode(content).decode()
            for i,start in enumerate(range(0,len(encoded),176)):
                t.send(name+'-delta-'+str(i),'printf %s '+shlex.quote(encoded[start:start+176])+(' >' if i==0 else ' >>')+d+'/delta64')
            command=f'r={d};printf \'%b\' "$(/usr/bin/od -v -c "$r/delta64" | /bin/sed \'s/^[0-7]* *//\' | awk -f "$r/d.awk")" >"$r/{name}.r2"'
            t.send(name+'-decode',command)
            got=t.send(name+'-digest',f'sha256sum {d}/{name}.r2')
            assert got.split()[0]==digest(content)
        t.send('delta-publish-once',f'r={d};test ! -e "$r/state" && chmod 700 "$r/common.sh.r2" "$r/manifest.sha256.r2" && mv "$r/common.sh.r2" "$r/common.sh" && mv "$r/manifest.sha256.r2" "$r/manifest.sha256"')
        t.send('patched-manifest',f'cd {d} && sha256sum -c manifest.sha256 >/dev/null && sh -n common.sh')
        state['staged']=True
    except BaseException as e:
        state['failure']=str(e);raise
    finally:
        runner.save(s,state,'stage.json');print(json.dumps(state),flush=True)
    return s.directory/'stage.json'

class NewPhaseTransfer(runner.StreamingTransfer):
    def send(self,label,command):
        if label in ('replay-ui-dispatch','replay-ui-result'):
            assert command.count('p=ui;')==1
            command=command.replace('p=ui;','p='+NEXT_PHASE+';',1)
        return super().send(label,command)

if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else ''
    if action.endswith('-r3'):
        FIX_SHARED_MAPS=True;PREVIOUS_PHASE='ui-r2';NEXT_PHASE='ui-r3'
        OUT=HERE/'build/runtime-maps-r3'
        action=action[:-3]
    elif action.endswith('-r4'):
        FIX_SHARED_MAPS=True;PREVIOUS_PHASE='ui-r3';NEXT_PHASE='ui-r4';PRIOR_FOLDER='runtime-maps-r3'
        OUT=HERE/'build/runtime-maps-r4'
        action=action[:-3]
    if action=='--build' and len(sys.argv)==2:
        r,_=build();print(json.dumps({'ready':True,'baselinePaths':74,'negativeChecks':5,'cameraRequests':0}))
    elif action=='--stage-delta' and len(sys.argv)==2: stage_delta()
    elif len(sys.argv)==3 and action=='--install-staged':
        runner.verify_package=verify_delta
        runner.StreamingTransfer=NewPhaseTransfer
        runner.install(sys.argv[2])
    else: raise SystemExit('No action')
