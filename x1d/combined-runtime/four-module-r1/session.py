"""复用已核验有界串行传输；本模块默认只做离线检查。"""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, hashlib, json, sys, time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE.parent))
spec=importlib.util.spec_from_file_location('combined_transport',HERE.parent/'transfer.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
transport.HERE=HERE
transport.REMOTE='/tmp/hbl-four-module-stage'
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/research'))
import formal_transfer as flash_transfer
import formal_sync_loader as capture
sys.path.insert(0,str(HERE))
import inspect_af
class Session(transport.Session):
    def command(self,label,command,timeout_ms=15000):
        if label=='services':command=command.replace('storage-daemon','system-manager')
        return super().command(label,command,timeout_ms)
def verify():
    p=json.loads((HERE/'build/package.json').read_text());data=(HERE/'build/combined.tar.gz').read_bytes()
    if hashlib.sha256(data).hexdigest()!=p['packageSha256']:raise ValueError('archive changed')
    for n,h in p['files'].items():
        if hashlib.sha256((HERE/'build/package'/n).read_bytes()).hexdigest()!=h:raise ValueError('package member changed')
    proof=json.loads((HERE/'CodeTests/install-validation.json').read_text())
    if not proof['passed'] or proof['installSha256']!=p['files']['flash/formal-install.sh'] or not capture.offline_ready():raise ValueError('offline verification stale')
    _,m,expected=inspect_af.source()
    af_code=set(range(m['base'],m['state_start'],4))|{a for a,_,_ in m['emulatorOnlyHooks']}
    if af_code & set(capture.WRITE_VALUES):raise ValueError('AF/flash collision')
    return p,data
def offline():
    p,data=verify()
    class Model:
        def __init__(self):self.calls=[]
        def command(self,label,command,timeout_ms=15000):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command,(label,len(command))
            self.calls.append(label)
            if label=='services':out='\n'.join(['active']*5)
            elif label.startswith('decode-observe'):out=p['packageSha256']+' archive'
            elif label=='extract-once':out='combined-package-verified'
            else:out=''
            return {'output':out}
    model=Model();transport.stage(model,p,data,lambda _:None)
    for phase in ('ui','observer'):flash_transfer.start_linux(model,phase);flash_transfer.linux_result(model,phase)
    result={'passed':True,'boundedRequests':len(model.calls),'afFlashWriteAreasDisjoint':True,'hardwareRequests':0,'packageSha256':p['packageSha256']}
    (HERE/'CodeTests/session-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
def install(resume=False,fresh_af=False):
    p,data=verify()
    proof=json.loads((HERE/'CodeTests/session-validation.json').read_text())
    if not proof['passed'] or proof['packageSha256']!=p['packageSha256']:raise ValueError('transport proof stale')
    s=Session('install');loader=capture.Loader()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=HERE/'build/sessions'/('installation-'+stamp+'.json')
    recovery=capture.HERE/'build'/('formal-four-module-recovery-'+stamp+'.json')
    state={'installed':False,'afPreserved':False,'packageSha256':p['packageSha256'],'temporaryOnly':True,'shotsTriggered':0,'flashTrialsTriggered':0,'recoveryRecord':recovery.relative_to(ROOT).as_posix()}
    def save(stage):
        state.update(stage=stage,linux=s.summary(),farmRequests=loader.io.requests,farmWrites=loader.io.writes,farmHandlesClosed=loader.io.closed)
        out.write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps({'stage':stage,'linuxRequests':state['linux']['requests'],'farmRequests':loader.io.requests}),flush=True)
    def health(label):
        r=s.command(label,'/tmp/hbl-wireless-flash/formal-system-check --require-held')
        if r['output'].strip()!='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1':raise RuntimeError('system not held and healthy')
    def phase(name,marker):
        flash_transfer.start_linux(s,name);save(name+'-dispatched-once')
        for i in range(140):
            time.sleep(1);result=flash_transfer.linux_result(s,name)
            if result!='pending':break
        else:raise RuntimeError('phase pending; no retry')
        if result.splitlines()!=['0',marker]:raise RuntimeError('Linux phase failed; consult exact rollback state')
    try:
        inspect_af.run(True);save('current-af-verified')
        if resume in ('bootstrapped','ui-ready'):
            condition='test -f formal-state/ui-hold-ready && test ! -e formal-state/install-complete' if resume=='ui-ready' else 'test ! -e formal-state'
            r=s.command('retry-package','cd /tmp/hbl-wireless-flash && '+condition+' && sha256sum -c manifest.sha256 >/dev/null && sha256sum manifest.sha256')
            if r['output'].split()[0]!=p['files']['flash/manifest.sha256']:raise ValueError('retry package mismatch')
        else:
            s.command('fresh-paths','test ! -e /tmp/hbl-wireless-flash && test ! -L /tmp/hbl-wireless-flash && test ! -e /run/hbl-four-module && test ! -L /run/hbl-four-module')
        if resume in ('bootstrapped','ui-ready'):
            pass
        elif resume:
            r=s.command('resume-archive-hash','sha256sum /tmp/hbl-four-module-stage/combined.tar.gz')
            if r['output'].split()[0]!=p['packageSha256']:raise ValueError('existing archive mismatch')
            s.command('resume-before-extract','test ! -e /tmp/hbl-four-module-stage/manifest.sha256 && test ! -e /tmp/hbl-four-module-stage/run.sh')
            r=s.command('resume-extract-once','cd /tmp/hbl-four-module-stage && tar xzf combined.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf combined-package-verified')
            if r['output']!='combined-package-verified':raise RuntimeError('existing package verification failed')
        else:
            transport.stage(s,p,data)
        save('archive-transferred-verified')
        if resume not in ('bootstrapped','ui-ready'):
            r=s.command('bootstrap-once','sh /tmp/hbl-four-module-stage/run.sh bootstrap')
            if r['output']!='four-module-bootstrap-verified':raise RuntimeError('bootstrap failed')
        save('bootstrap-verified')
        if resume!='ui-ready':
            phase('ui','formal-ui-hold-ready-default-off')
        else:
            pid=s.command('current-gui-pid','systemctl show -p MainPID victory-gui')['output'].strip().split('=')[1]
            if not pid.isdigit() or int(pid)<1:raise ValueError('GUI PID')
            gates=s.command('current-ui-gates','cat /run/hbl-four-module/ui.status /run/hbl-four-module/replay.status')['output'].splitlines()
            if gates!=['ui-resident-ready-resources6-components5-pools3-pages23-rows-diag1 pid='+pid,'replay-page-ready-resources7-components7-pages2 pid='+pid]:raise ValueError('current UI/replay gates')
        health('ui-held');save('ui-and-replay-ready')
        if fresh_af:
            import scratch_cleanup
            scratch_cleanup.live()
            save('fresh-af-scratch-cleared-and-af-verified')
        from farm_diagnostic_binary import FarmApplication
        loader.prepare(FarmApplication().data,recovery);save('flash-arena-and-original-hooks-verified')
        phase('observer','formal-linux-ready-default-off');health('observer-held')
        inspect_af.run(True);save('af-preserved-after-service-restart')
        loader.probe();save('cache-probe-restored')
        health('before-hooks');loader.install_disarmed();save('flash-installed-disarmed')
        health('before-arm');loader.arm();loader.verify(1);save('flash-armed')
        inspect_af.run(True);state['afPreserved']=True;health('final-health')
        r=s.command('final-linux','d=/tmp/hbl-wireless-flash;cat "$d/formal-runtime.status" "$d/formal-worker.status" "$d/formal-observer.status";systemctl is-active victory-gui msg2dbus-farm')
        output=r['output']
        if not all(x in output for x in ('formal-ui-loaded-default-off','formal-worker-ready-default-off','master=0 radio-held=0 radio-busy=0 same-process=1','stage=ready meta=1 observe=1')) or output.splitlines()[-2:]!=['active','active']:raise RuntimeError('final Linux differs')
        save('all-four-verified-controls-locked')
        r=s.command('enable-once','d=/tmp/hbl-wireless-flash;umask 077;test ! -e "$d/formal-enable.ready" && test ! -L "$d/formal-enable.ready" && (set -C;printf ready >"$d/formal-enable.ready") && printf gate-requested')
        if r['output']!='gate-requested':raise RuntimeError('enable unknown; no retry')
        for i in range(20):
            time.sleep(.2)
            r=s.command('enable-observe','d=/tmp/hbl-wireless-flash;if test -f "$d/formal-enable.confirmed";then cat "$d/formal-enable.confirmed";systemctl is-active victory-gui msg2dbus-farm;else printf pending;fi')
            if r['output']!='pending':break
        if r['output'].splitlines()!=['ready','active','active']:raise RuntimeError('enable not confirmed')
        health('before-release')
        s.command('release-once','umask 077;set -C;printf release >/tmp/hbl-wireless-flash/formal-state/hold.release')
        state.update(installed=True,holdReleased=True,flashMasterDefaultOff=True)
        save('ready-for-user-manual-testing');return state
    except Exception as e:
        state.update(error=type(e).__name__+': '+str(e),lastStage=state.get('stage'),automaticRetry=False)
        save('stopped-for-review');raise
if __name__=='__main__':
    if sys.argv[1:]==['--install']:print(json.dumps(install()))
    elif sys.argv[1:]==['--install-after-af']:print(json.dumps(install(fresh_af=True)))
    elif sys.argv[1:]==['--resume-transferred']:print(json.dumps(install(True)))
    elif sys.argv[1:]==['--resume-transferred-after-af']:print(json.dumps(install(True,fresh_af=True)))
    elif sys.argv[1:]==['--install-bootstrapped']:print(json.dumps(install('bootstrapped')))
    elif sys.argv[1:]==['--continue-ui-ready']:print(json.dumps(install('ui-ready')))
    elif not sys.argv[1:]:print(json.dumps(offline()))
    else:raise SystemExit('unsupported arguments')
