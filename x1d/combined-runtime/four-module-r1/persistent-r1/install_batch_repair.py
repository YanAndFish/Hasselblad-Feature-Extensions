"""固定小型启动修复包；不重启服务或重复当前 RAM 装载。"""
from pathlib import Path
import base64,hashlib,io,json,shlex,sys,tarfile,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent));import session
OUT=HERE/'build/batch-repair-r6';REMOTE='/tmp/hbl-batch-r6'
NAMES=('runtime/libhbl-formal-observer.so','runtime/persistent-check','runtime/manifest.sha256','manifest.sha256','installed.manifest.sha256')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def prepare():
    assert Path.cwd().resolve()==ROOT
    proof=read(HERE/'CodeTests/batch-repair-validation.json')
    assert proof['passed'] and proof['scriptSha256']==sha((HERE/'repair-batch.sh').read_bytes())
    radio=read(HERE/'CodeTests/radio-async-validation.json')
    assert radio['passed'] and radio['scriptSha256']==sha((HERE/'boot-prepare-radio.sh').read_bytes())
    coord=read(HERE/'CodeTests/boot-coordinate-validation.json')
    assert coord['passed'] and coord['scripts']['boot-coordinate.sh']==sha((HERE/'boot-coordinate.sh').read_bytes())
    old=read(HERE/'build/wait-revert-r5/persistent-package.json')
    new=read(HERE/'build/persistent-package.json')
    assert not set(old['files'])-set(new['files'])
    changed={n for n in new['files'] if old['files'].get(n)!=new['files'][n]}
    assert changed==set(NAMES[:-1]),changed
    files={'files/'+n:(HERE/'build/persistent-package'/n).read_bytes() for n in NAMES[:-1]}
    for n in NAMES[:-1]:assert sha(files['files/'+n])==new['files'][n]
    files['files/installed.manifest.sha256']=(new['manifestSha256']+'\n').encode()
    files['old-pin']=(old['manifestSha256']+'\n').encode()
    files['repair-batch.sh']=(HERE/'repair-batch.sh').read_bytes()
    files['batch-wire-check']=(HERE/'build/formal-flash-program/batch-wire-check').read_bytes()
    build=read(HERE/'build/formal-flash-program/client-build.json')
    assert sha(files['batch-wire-check'])==build['outputs']['batch-wire-check']['sha256']
    for name,digest in read(HERE/'build/batch-model/validation.json')['sources'].items():assert sha((HERE/name).read_bytes())==digest,name
    files['repair-manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    OUT.mkdir(exist_ok=True)
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for n,b in files.items():
            p=OUT/'package'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o600;archive.addfile(m,io.BytesIO(b))
    data=stream.getvalue();(OUT/'repair.tgz').write_bytes(data)
    report={'archiveSha256':sha(data),'bytes':len(data),'oldManifest':old['manifestSha256'],'newManifest':new['manifestSha256'],'changedFiles':list(NAMES),'installed':False,'coldBootVerified':False}
    (OUT/'package.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return data,report
def run():
    data,report=prepare()
    if (OUT/'installation.json').exists():raise RuntimeError('existing attempt; inspect only')
    s=session.Session('batch-repair');seen=set()
    def cmd(label,command):
        assert label not in seen and 0<len(command.encode('ascii'))<=231 and '\n' not in command
        seen.add(label);return s.command(label,command)['output'].strip()
    def save(stage):
        report.update(stage=stage,session=s.summary())
        (OUT/'installation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'stage':stage,'requests':s.summary()['requests']}),flush=True)
    try:
        assert cmd('verify-installed','sh /opt/hbl-four-module-v1/install.sh status')=='persistent-files-verified-root-readonly'
        report['beforePids']=cmd('pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        assert cmd('services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon').splitlines()==['active']*5
        assert cmd('old-pin','cat /opt/hbl-four-module-v1/installed.manifest.sha256')==report['oldManifest']
        assert cmd('loader','cat /run/hbl-four-module/boot-loader.status').startswith('state=ready phase=modules-ready ')
        cmd('completed','test ! -e /media/data/hbl-four-module/boot-incomplete && test ! -L /media/data/hbl-four-module/boot-incomplete')
        cmd('mkdir','umask 077;test ! -e '+REMOTE+' && test ! -L '+REMOTE+' && mkdir -m 700 '+REMOTE)
        save('preflight-passed')
        decoder=session.transport.DECODER
        for i,start in enumerate(range(0,len(decoder),90)):
            cmd('decoder-'+str(i),'printf %s '+shlex.quote(decoder[start:start+90])+(' >' if i==0 else ' >>')+REMOTE+'/d.awk')
        encoded=base64.b64encode(data).decode()
        for i,start in enumerate(range(0,len(encoded),170)):
            cmd('chunk-'+str(i),"printf '%s\\n' "+shlex.quote(encoded[start:start+170])+(' >' if i==0 else ' >>')+REMOTE+'/p64')
        cmd('decode','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/repair.tgz";sha256sum "$r/repair.tgz" >"$r/decoded") </dev/null >/dev/null 2>&1 &')
        save('transferred')
        for i in range(60):
            time.sleep(1)
            result=cmd('decode-check-'+str(i),'r='+REMOTE+';if test -f "$r/decoded";then cat "$r/decoded";else echo pending;fi')
            if result!='pending':break
        assert result.split()[0]==report['archiveSha256']
        cmd('extract','cd '+REMOTE+' && tar xzf repair.tgz && sha256sum -c repair-manifest.sha256 >/dev/null && sh -n repair-batch.sh')
        cmd('executable','chmod 700 '+REMOTE+'/files/runtime/persistent-check '+REMOTE+'/batch-wire-check')
        assert 'hardware=0' in cmd('relocation-selfcheck',REMOTE+'/files/runtime/persistent-check --relocation')
        assert 'hardware=0' in cmd('wire-selfcheck',REMOTE+'/batch-wire-check')
        save('target-selfchecks-passed')
        cmd('dispatch','r='+REMOTE+';test ! -e "$r/dispatched" && touch "$r/dispatched" && (sh "$r/repair-batch.sh" >"$r/result" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &')
        save('file-update-dispatched')
        for i in range(60):
            time.sleep(1)
            result=cmd('result-'+str(i),'r='+REMOTE+';if test -f "$r/exit";then cat "$r/exit" "$r/result";else echo pending;fi')
            if result!='pending':break
        report['deviceResult']=result
        assert result.splitlines()==['0','batch-files-repaired-next-boot'],result
        assert cmd('final-verify','sh /opt/hbl-four-module-v1/install.sh status')=='persistent-files-verified-root-readonly'
        assert cmd('final-pin','cat /opt/hbl-four-module-v1/installed.manifest.sha256')==report['newManifest']
        report['afterPids']=cmd('final-pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        assert report['afterPids']==report['beforePids']
        assert cmd('final-services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon').splitlines()==['active']*5
        report.update(installed=True,rootReadOnly=True,currentProcessesPreserved=True,automaticCameraReboots=0,farmMemoryWrites=0,coldBootVerified=False)
        save('repaired-verified-awaiting-normal-power-cycle')
    except BaseException as e:
        report['error']=str(e);save('stopped-for-review');raise
if __name__=='__main__':
    if sys.argv[1:]==['--prepare']:print(json.dumps(prepare()[1]))
    elif sys.argv[1:]==['--run']:run()
    else:raise SystemExit('select --prepare or --run')
