"""仅替换已安装组合包的 observer；串行、默认离线、失败不重放。"""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,io,json,shlex,sys,tarfile,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import session
WORK=HERE/'mechanical-exit-idle';OUT=WORK/'update';REMOTE='/tmp/hbl-mech-exit-r1'
D='/tmp/hbl-wireless-flash';P='d='+D+';r='+REMOTE+';'
OLD='fb5676a9419b7e20e3d8b147add5d81e5123ffaaa6851228ab2549d54bd5ddf1'
def sha(b):return hashlib.sha256(b).hexdigest()
def prepare():
    proof=json.loads((WORK/'verification.json').read_text());assert proof['passed'] and proof['sourceId']==3
    lib=(WORK/'build/formal-flash-program/libhbl-formal-observer.so').read_bytes();assert sha(lib)==proof['observerSha256']
    old=(HERE/'build/package/flash/manifest.sha256').read_bytes()
    anchor=(OLD+'  libhbl-formal-observer.so\n').encode();assert old.count(anchor)==1
    new=old.replace(anchor,(sha(lib)+'  libhbl-formal-observer.so\n').encode())
    files={'observer.so':lib,'manifest.next':new,'package-manifest.next':(sha(new)+'\n').encode()}
    files['update.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    OUT.mkdir(exist_ok=True);stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as t:
        for n,b in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o600;t.addfile(m,io.BytesIO(b))
    data=stream.getvalue();(OUT/'update.tar.gz').write_bytes(data)
    r={'archiveSha256':sha(data),'archiveBytes':len(data),'oldObserverSha256':OLD,'newObserverSha256':sha(lib),
       'oldManifestSha256':sha(old),'newManifestSha256':sha(new),'sourceId':3,'files':{n:sha(b) for n,b in files.items()},'hardwareRequests':0}
    (OUT/'package.json').write_text(json.dumps(r,indent=2)+'\n');return r
def inputs():
    p=json.loads((OUT/'package.json').read_text());data=(OUT/'update.tar.gz').read_bytes()
    assert sha(data)==p['archiveSha256'] and p['oldObserverSha256']==OLD
    return p,data
def run(s,p,data,pause=time.sleep,audit=lambda:None,progress=lambda x:None):
    labels=[]
    def cmd(label,command,expected=None):
        assert label not in labels,label
        labels.append(label)
        assert 0<len(command.encode('ascii'))<=231 and '\n' not in command,(label,len(command))
        result=s.command(label,command)['output'].strip()
        if expected is not None and result!=expected:raise RuntimeError('unexpected reply: '+label)
        return result
    def health(label):
        value=cmd(label,D+'/formal-system-check --require-ui-stage')
        if value not in ('system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0','system=4 suc=0 farm=0 pwr=0 ui-power=1 hold=0'):raise RuntimeError('system not stable')
    def pid(label,service):
        value=cmd(label,'systemctl show -p MainPID '+service)
        assert value.startswith('MainPID=') and value[8:].isdigit() and int(value[8:])>0
        return value[8:]
    cmd('services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon','\n'.join(['active']*5))
    cmd('owned',P+'test -d "$d" && test ! -L "$d" && test "$(stat -c %u:%a "$d")" = 0:700')
    cmd('old-manifest',P+'sha256sum "$d/manifest.sha256"',p['oldManifestSha256']+'  '+D+'/manifest.sha256')
    cmd('old-library',P+'sha256sum "$d/libhbl-formal-observer.so"',OLD+'  '+D+'/libhbl-formal-observer.so')
    cmd('old-package-check',P+'cd "$d" && sha256sum -c manifest.sha256 >/dev/null && test -f formal-state/install-complete && test -f formal-state/hold.release && test ! -e formal-stop.request')
    health('before-transfer');gui=pid('gui-before','victory-gui');farm=pid('farm-before','msg2dbus-farm')
    audit()
    cmd('create-stage','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r"')
    decoder=session.transport.DECODER
    for i,start in enumerate(range(0,len(decoder),90)):
        cmd('decoder-'+str(i),'printf %s '+shlex.quote(decoder[start:start+90])+(' >' if i==0 else ' >>')+REMOTE+'/d.awk')
    encoded=base64.b64encode(data).decode();chunks=[encoded[i:i+176] for i in range(0,len(encoded),176)]
    for i,part in enumerate(chunks):
        # 保留 base64 四字节边界并逐行输入，避免整包单行 length/substring 的重复扫描。
        cmd('chunk-'+str(i),"printf '%s\\n' "+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
    progress('small-file-transferred')
    cmd('decode-once','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/update.tar.gz";sha256sum "$r/update.tar.gz" >"$r/decode.sha") </dev/null >/dev/null 2>&1 &')
    for i in range(60):
        pause(1);value=cmd('decode-observe-'+str(i),'r='+REMOTE+';if test -f "$r/decode.sha";then cat "$r/decode.sha";else printf pending;fi')
        if value!='pending':break
    else:raise RuntimeError('decode pending; do not repeat')
    assert value==p['archiveSha256']+'  '+REMOTE+'/update.tar.gz'
    cmd('extract-once','cd '+REMOTE+' && tar xzf update.tar.gz && sha256sum -c update.sha256 >/dev/null')
    value=cmd('target-selfcheck',P+'HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD="$r/observer.so" "$d/formal-sync-hook-check"')
    assert value.startswith('sync-hook-selftest: own=10 forwarded=') and value.endswith(' status=1 hardware=0')
    health('before-stop')
    cmd('backup',P+'cp "$d/libhbl-formal-observer.so" "$r/previous.so" && cp "$d/manifest.sha256" "$r/previous.manifest" && cp "$d/formal-state/package-manifest.sha256" "$r/previous.package"')
    cmd('backup-hash',P+'sha256sum "$r/previous.so"',OLD+'  '+REMOTE+'/previous.so')
    cmd('stop-worker-once',P+'umask 077;set -C;printf stop >"$d/formal-stop.request"')
    expected='formal-worker-stopped-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid='+farm
    for i in range(30):
        pause(.2);value=cmd('stop-observe-'+str(i),P+'cat "$d/formal-worker.status"')
        if value==expected:break
        if 'stop-failed' in value:raise RuntimeError('worker stop failed')
    else:raise RuntimeError('worker stop unconfirmed')
    progress('worker-stopped-radio-released')
    health('stopped-health')
    cmd('stop-service-once','systemctl stop msg2dbus-farm')
    cmd('service-stopped','systemctl show -p MainPID msg2dbus-farm','MainPID=0')
    cmd('service-inactive','test "$(systemctl is-active msg2dbus-farm)" = inactive')
    cmd('archive-enable',P+'mv "$d/formal-enable.ready" "$r/old.ready" && mv "$d/formal-enable.confirmed" "$r/old.confirmed"')
    cmd('copy-candidate',P+'test ! -e "$d/observer.next" && cp "$r/observer.so" "$d/observer.next" && chmod 600 "$d/observer.next"')
    cmd('candidate-hash',P+'sha256sum "$d/observer.next"',p['newObserverSha256']+'  '+D+'/observer.next')
    cmd('replace-library-once',P+'mv "$d/observer.next" "$d/libhbl-formal-observer.so"')
    cmd('replace-manifest',P+'cp "$r/manifest.next" "$d/manifest.next" && mv "$d/manifest.next" "$d/manifest.sha256"')
    cmd('replace-manifest-record',P+'cp "$r/package-manifest.next" "$d/formal-state/package.next" && mv "$d/formal-state/package.next" "$d/formal-state/package-manifest.sha256"')
    cmd('updated-package-check',P+'cd "$d" && sha256sum -c manifest.sha256 >/dev/null')
    cmd('archive-stop',P+'mv "$d/formal-stop.request" "$r/old.stop"')
    pause(3)
    cmd('start-service-once','systemctl start msg2dbus-farm')
    newfarm=pid('farm-after','msg2dbus-farm');assert newfarm!=farm
    expected='formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid='+newfarm
    for i in range(30):
        pause(.3);value=cmd('ready-observe-'+str(i),P+'cat "$d/formal-worker.status"')
        if value==expected:break
    else:raise RuntimeError('new worker not ready')
    cmd('observer-ready',P+'cat "$d/formal-observer.status"','stage=ready meta=1 observe=1')
    cmd('observer-mapped','grep -q '+D+'/libhbl-formal-observer.so /proc/'+newfarm+'/maps')
    health('after-reload');audit()
    assert pid('gui-after','victory-gui')==gui
    cmd('enable-new-once',P+'umask 077;set -C;printf ready >"$d/formal-enable.ready"')
    for i in range(20):
        pause(.2);value=cmd('enable-observe-'+str(i),P+'if test -f "$d/formal-enable.confirmed";then cat "$d/formal-enable.confirmed";else printf pending;fi')
        if value=='ready':break
    else:raise RuntimeError('new enable unconfirmed')
    health('final-health')
    cmd('final-services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon','\n'.join(['active']*5))
    progress('ready-for-user-manual-testing')
    return {'installed':True,'sourceId':3,'observerSha256':p['newObserverSha256'],'guiPreserved':True,'afAndFlashRamPreserved':True,
            'temporaryOnly':True,'flashMasterDefaultOff':True,'commands':len(labels),'shotsTriggered':0,'flashTrialsTriggered':0}
def offline():
    p,data=inputs()
    class Model:
        def __init__(self,fail=None):self.labels=[];self.fail=fail
        def command(self,label,command):
            self.labels.append(label)
            if label==self.fail:raise RuntimeError('injected uncertain response')
            value=''
            if label in ('services','final-services'):value='\n'.join(['active']*5)
            elif label in ('before-transfer','before-stop','stopped-health','after-reload','final-health'):value='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0'
            elif label in ('gui-before','gui-after'):value='MainPID=3343'
            elif label=='farm-before':value='MainPID=3794'
            elif label=='farm-after':value='MainPID=4000'
            elif label=='service-stopped':value='MainPID=0'
            elif label=='old-manifest':value=p['oldManifestSha256']+'  '+D+'/manifest.sha256'
            elif label=='old-library':value=OLD+'  '+D+'/libhbl-formal-observer.so'
            elif label=='backup-hash':value=OLD+'  '+REMOTE+'/previous.so'
            elif label=='candidate-hash':value=p['newObserverSha256']+'  '+D+'/observer.next'
            elif label.startswith('decode-observe'):value=p['archiveSha256']+'  '+REMOTE+'/update.tar.gz'
            elif label=='target-selfcheck':value='sync-hook-selftest: own=10 forwarded=10 status=1 hardware=0'
            elif label.startswith('stop-observe'):value='formal-worker-stopped-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=3794'
            elif label.startswith('ready-observe'):value='formal-worker-ready-default-off\nmaster=0 radio-held=0 radio-busy=0 same-process=1 pid=4000'
            elif label=='observer-ready':value='stage=ready meta=1 observe=1'
            elif label.startswith('enable-observe'):value='ready'
            return {'output':value}
    normal=Model();result=run(normal,p,data,lambda _:None)
    assert normal.labels.index('stop-observe-0')<normal.labels.index('replace-library-once')<normal.labels.index('start-service-once')<normal.labels.index('enable-new-once')
    failures=['old-manifest','target-selfcheck','stop-observe-0','stop-service-once','replace-library-once','start-service-once','ready-observe-0','enable-new-once']
    for point in failures:
        m=Model(point)
        try:run(m,p,data,lambda _:None)
        except RuntimeError:pass
        else:raise AssertionError(point)
        assert m.labels[-1]==point and m.labels.count(point)==1
    # 以真实 awk/printf 验证逐行 base64 解码，包含所有字节及尾部补位。
    shell=ROOT/'.research-cache/x1d-1.25.0/toolchain' # shell 来源复用已有安装测试环境，见下方导入。
    import importlib.util,subprocess
    spec=importlib.util.spec_from_file_location('observer_shell_test',ROOT/'x1d/wireless-flash/CodeTests/formal_install.test.py')
    t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
    fixture=bytes(range(256))*3+b'end';encoded=base64.b64encode(fixture).decode()
    (OUT/'decode-test.p64').write_text('\n'.join(encoded[i:i+176] for i in range(0,len(encoded),176))+'\n',encoding='ascii')
    (OUT/'decode-test.awk').write_text(session.transport.DECODER,encoding='ascii')
    command='printf \'%b\' "$(awk -f '+shlex.quote((OUT/'decode-test.awk').as_posix())+' '+shlex.quote((OUT/'decode-test.p64').as_posix())+')"'
    r=subprocess.run([str(t.SHELL),'-c',command],capture_output=True);assert r.returncode==0 and r.stdout==fixture
    proof={'passed':True,'normalCommands':result['commands'],'uncertainResponseCases':failures,'lineDecoderBinaryExact':True,
           'sourceSha256':sha(Path(__file__).read_bytes()),'archiveSha256':p['archiveSha256'],'hardwareRequests':0}
    (OUT/'validation.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
def live():
    assert Path.cwd().resolve()==ROOT
    p,data=inputs();proof=json.loads((OUT/'validation.json').read_text())
    assert proof['passed'] and proof['sourceSha256']==sha(Path(__file__).read_bytes()) and proof['archiveSha256']==p['archiveSha256']
    s=session.Session('replace-observer');audits=[]
    def audit():
        af=session.inspect_af.run(True)
        class ReadOnly(session.capture.FixedIO):
            def exchange(self,kind,a=None,v=None):
                if kind!='read':raise ValueError('read-only preservation audit')
                return super().exchange(kind,a,v)
        loader=session.capture.Loader(ReadOnly());loader.verify(1)
        assert loader.io.writes==0 and loader.io.closed
        audits.append({'af':af,'flashRequests':loader.io.requests,'flashWrites':loader.io.writes,'flashClosed':loader.io.closed})
    report={'installed':False,'sourceId':3,'archiveSha256':p['archiveSha256']}
    path=OUT/('installation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    def save(stage):
        report.update(stage=stage,linux=s.summary(),audits=audits);path.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'stage':stage,'linuxRequests':s.summary()['requests']}),flush=True)
    try:report.update(run(s,p,data,audit=audit,progress=save));save('completed')
    except BaseException as e:
        report.update(error=type(e).__name__+': '+str(e),automaticRetry=False);save('stopped-for-review');raise
    return report
if __name__=='__main__':
    actions={'--prepare':prepare,'--test':offline,'--replace-temporary':live}
    assert len(sys.argv)==2 and sys.argv[1] in actions
    print(json.dumps(actions[sys.argv[1]]()))
