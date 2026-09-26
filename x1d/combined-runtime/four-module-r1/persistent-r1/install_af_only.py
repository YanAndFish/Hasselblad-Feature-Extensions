"""固定小型启动修复包；不重启服务或重复当前 RAM 装载。"""
from pathlib import Path
import base64,hashlib,io,json,shlex,sys,tarfile,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent));import session
OUT=HERE/'build/af-only';REMOTE='/tmp/hbl-af-r1'
NAMES=('runtime/libhbl-formal-observer.so','runtime/persistent-check','runtime/manifest.sha256','manifest.sha256','installed.manifest.sha256')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def prepare():
    out=HERE/'build/af-only'
    meta=read(out/'package.json');data=(out/'transfer.tgz').read_bytes()
    assert sha(data)==meta['sha256']
    for n,h in meta['sourceHashes'].items():assert sha((HERE/n).read_bytes())==h
    report=dict(meta,archiveSha256=meta['sha256'],oldManifest=(out/'old-pin').read_text().strip(),newManifest=sha((out/'package/manifest.sha256').read_bytes()))
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
        cmd('verify-installed','cd /opt/hbl-four-module-v1 && sha256sum -c manifest.sha256 >/dev/null && test ! -e enabled && test -f enabled.af-test')
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
        cmd('extract','cd '+REMOTE+' && tar xzf repair.tgz && sha256sum -c transfer.sha256 >/dev/null && sh -n install.sh')
        cmd('ui-link-check','LD_PRELOAD='+REMOTE+'/package/libhbl-af-ui.so /bin/true')
        cmd('loader-link-check','LD_PRELOAD='+REMOTE+'/package/libhbl-af-loader.so /bin/true')
        save('target-selfchecks-passed')
        cmd('dispatch','r='+REMOTE+';test ! -e "$r/dispatched" && touch "$r/dispatched" && (sh "$r/install.sh" >"$r/result" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &')
        save('file-update-dispatched')
        for i in range(60):
            time.sleep(1)
            result=cmd('result-'+str(i),'r='+REMOTE+';if test -f "$r/exit";then cat "$r/exit" "$r/result";else echo pending;fi')
            if result!='pending':break
        report['deviceResult']=result
        assert result.splitlines()==['0','af-only-installed-awaiting-restart'],result
        cmd('final-verify','. /opt/hbl-af-only-v1/common.sh;verify')
        assert cmd('final-pin',"sha256sum /opt/hbl-af-only-v1/manifest.sha256 | cut -d' ' -f1")==report['newManifest']
        report['afterPids']=cmd('final-pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        assert report['afterPids']==report['beforePids']
        assert cmd('final-services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon').splitlines()==['active']*5
        cmd('root-ro',"awk '$2==\"/\" && $4~/(^|,)ro(,|$)/ {yes=1} END{exit !yes}' /proc/mounts")
        report.update(installed=True,rootReadOnly=True,currentProcessesPreserved=True,automaticCameraReboots=0,farmMemoryWrites=0,coldBootVerified=False)
        save('repaired-verified-awaiting-normal-power-cycle')
    except BaseException as e:
        report['error']=str(e);save('stopped-for-review');raise
if __name__=='__main__':
    if sys.argv[1:]==['--prepare']:print(json.dumps(prepare()[1]))
    elif sys.argv[1:]==['--run']:run()
    else:raise SystemExit('select --prepare or --run')
