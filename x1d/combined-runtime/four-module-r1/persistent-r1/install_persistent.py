"""传送固定永久包，运行机内无硬件自检，再单次安装启动文件。"""
from pathlib import Path
import base64,hashlib,json,shlex,sys,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent));import session
sys.path.insert(0,str(HERE.parent/'mechanical-calibration-r1'));import install_candidate
REMOTE='/tmp/hbl-persistent-r1'
OUT=HERE/'build/persistent-install'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def run():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    data=(HERE/'build/persistent-package.tgz').read_bytes();report=read(HERE/'build/persistent-package.json')
    if sha(data)!=report['archiveSha256']:raise RuntimeError('archive identity')
    for n,h in report['files'].items():
        if sha((HERE/'build/persistent-package'/n).read_bytes())!=h:raise RuntimeError('package output changed')
    if OUT.exists():raise RuntimeError('single install record already exists; inspect without replay')
    OUT.mkdir();report.update(installed=False,coldBootVerified=False,packagePreparationHardwareRequests=report.pop('hardwareRequests'),verificationRequests=0)
    s=session.Session('persistent-files-install');seen=set()
    def cmd(label,command):
        if label in seen or not 0<len(command.encode('ascii'))<=231 or '\n' in command:raise RuntimeError('bounded distinct command')
        seen.add(label);return s.command(label,command)['output'].strip()
    def save(stage):
        report.update(stage=stage,session=s.summary(),hardwareRequests=s.summary()['requests']+report['verificationRequests'])
        (OUT/'installation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'stage':stage,'linuxRequests':s.summary()['requests'],'installed':report['installed']}),flush=True)
    try:
        health=cmd('health','/tmp/hbl-wireless-flash/formal-system-check --require-ui-stage')
        if health!='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0':raise RuntimeError('active original runtime required')
        report['beforePids']=cmd('pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        cmd('fresh','test ! -e '+REMOTE+' && test ! -L '+REMOTE+' && test ! -e /opt/hbl-four-module-v1')
        before=install_candidate.audit();(OUT/'preservation-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
        report['verificationRequests']+=before['af']['hardwareRequests']+before['flashRequests']
        save('current-memory-verified')
        cmd('mkdir','umask 077;mkdir -m 700 '+REMOTE)
        decoder=session.transport.DECODER
        for i,start in enumerate(range(0,len(decoder),90)):
            cmd('decoder-'+str(i),'printf %s '+shlex.quote(decoder[start:start+90])+(' >' if i==0 else ' >>')+REMOTE+'/d.awk')
        encoded=base64.b64encode(data).decode()
        total=(len(encoded)+179)//180
        for i,start in enumerate(range(0,len(encoded),180)):
            cmd('chunk-'+str(i),"printf '%s\\n' "+shlex.quote(encoded[start:start+180])+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if i%64==63:
                report['transferChunks']=[i+1,total];save('transferring')
        cmd('decode-once','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/package.tgz";sha256sum "$r/package.tgz" >"$r/decoded.sha") </dev/null >/dev/null 2>&1 &')
        save('transferred-decoding')
        result='pending'
        for i in range(90):
            time.sleep(1)
            result=cmd('decoded-'+str(i),'r='+REMOTE+';if test -f "$r/decoded.sha";then cat "$r/decoded.sha";else printf pending;fi')
            if result!='pending':break
        if result.split()[0]!=report['archiveSha256']:raise RuntimeError('decoded archive mismatch')
        cmd('extract','cd '+REMOTE+' && tar xzf package.tgz && sha256sum -c manifest.sha256 >/dev/null && sha256sum -c baseline.sha256 >/dev/null')
        cmd('chmod','chmod 700 '+REMOTE+'/runtime/persistent-check '+REMOTE+'/runtime/formal-sync-hook-check')
        report['relocationSelfcheck']=cmd('native-relocation',REMOTE+'/runtime/persistent-check --relocation')
        if report['relocationSelfcheck']!='persistent-relocation-selftest links=3 hardware=0':raise RuntimeError('target relocation selfcheck')
        report['storeSelfcheck']=cmd('native-store',REMOTE+'/runtime/persistent-check --store')
        if report['storeSelfcheck']!='persistent-store-selftest roundtrip=1 invalid=1 truncated=1 symlink=1 hardware=0':raise RuntimeError('target settings store selfcheck')
        report['observerSelfcheck']=cmd('native-observer','r='+REMOTE+';HBL_FORMAL_SYNC_SELFTEST=1 LD_PRELOAD="$r/runtime/libhbl-formal-observer.so" "$r/runtime/formal-sync-hook-check"')
        if not report['observerSelfcheck'].startswith('sync-hook-selftest: own=10 forwarded=') or not report['observerSelfcheck'].endswith('status=1 hardware=0'):raise RuntimeError('target observer selfcheck')
        save('target-selfchecks-passed')
        cmd('pin-manifest','printf %s '+report['manifestSha256']+' >'+REMOTE+'/expected')
        command='r='+REMOTE+';test ! -e "$r/dispatched" && touch "$r/dispatched" && (sh "$r/install.sh" install "$(cat "$r/expected")" >"$r/install.log" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &'
        cmd('install-once',command)
        save('persistent-file-transaction-dispatched')
        result='pending'
        for i in range(60):
            time.sleep(1)
            result=cmd('install-result-'+str(i),'r='+REMOTE+';if test -f "$r/exit";then cat "$r/exit";cat "$r/install.log";else printf pending;fi')
            if result!='pending':break
        report['deviceResult']=result
        if result.splitlines()!=['0','persistent-files-installed-next-boot']:raise RuntimeError('installation did not report exact completion; do not replay')
        report['installed']=True;save('persistent-files-installed')
        result=cmd('installed-status','sh /opt/hbl-four-module-v1/install.sh status')
        if result!='persistent-files-verified-root-readonly':raise RuntimeError('persistent file verification')
        report['afterPids']=cmd('after-pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        if report['afterPids']!=report['beforePids']:raise RuntimeError('current process identity changed')
        after=install_candidate.audit();(OUT/'preservation-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
        report['verificationRequests']+=after['af']['hardwareRequests']+after['flashRequests']
        health=cmd('final-health','/tmp/hbl-wireless-flash/formal-system-check --require-ui-stage')
        if health!='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0':raise RuntimeError('final system health')
        report.update(afAndFlashPreserved=True,rootRestoredReadOnly=True,currentProcessesPreserved=True,automaticCameraReboots=0,coldBootVerified=False,farmMemoryWrites=0)
        save('installed-verified-awaiting-user-power-cycle')
    except BaseException as error:
        report['error']=str(error);save('stopped-for-review');raise

if __name__=='__main__':
    if sys.argv[1:]!=['--run']:raise SystemExit('select --run')
    run()
