"""本轮首次组合安装的单一串行协调器；默认只核本地输入。"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import build_package
import transfer
import formal_sync_loader as capture

HEALTH='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1'
MARKERS={'preflight':'combined-preflight-ready','ui':'combined-ui-ready-default-off',
         'observer':'combined-observer-ready-default-off','provider':'combined-provider-ready-default-off',
         'replay-prepare':'replay-backend-prepared','replay-config':'replay-backend-config-ready',
         'replay-jpeg':'replay-backend-jpeg-ready','enable':'combined-user-controls-enabled-default-off',
         'release':'combined-installed-ready-for-user'}

def verify_after_services(contract,flash_sequence,io):
    """新只读句柄核验，绝不在已关闭的 AF 安装事件链上追加请求。"""
    manifest=contract.candidate
    expected=dict(contract.flash_expected)
    expected.update({a:v for a,v in contract.candidate_words.items() if a<manifest['state_start']})
    expected.update({a:new for a,_,new in manifest['emulatorOnlyHooks']})
    # 执行回执常量来自已冻结的 AF 模块，不复制推测值。
    import upgrade_primitives
    expected[contract.exec_ack]=upgrade_primitives.EXEC_MAGIC
    expected[contract.flash['record']+12]=flash_sequence
    for index,(address,value) in enumerate(sorted(expected.items())):
        if index%256==0:
            io.hold_permitted=True
            try:io.check_hold('final-read-'+str(index))
            finally:io.hold_permitted=False
        if io.read(address)!=value:raise RuntimeError('final AF/flash code or exposure sequence differs')
    for address in (0x6bb46c,0x6bb598,0x2adc78,0x2adc8c):
        mask,value=contract.guards[address]
        if io.read(address)&mask!=value:raise RuntimeError('final AF/profile not idle')
    for address,value in ((upgrade_primitives.CB,upgrade_primitives.ORIG_CB),(upgrade_primitives.ARG,upgrade_primitives.ORIG_ARG)):
        if io.read(address)!=value:raise RuntimeError('final callback not original')
    return {'requests':io.requests,'writeRequests':io.writes,'allHandlesClosed':io.closed}

def ready():
    report,_=build_package.verify()
    if not capture.offline_ready():raise RuntimeError('fixed flash validation stale')
    sys.path.insert(0,str(ROOT/'x1d/af-experiment/camera-settings-r1'))
    import settings_loader
    if settings_loader.readiness() is None:raise RuntimeError('AF delivery validation stale')
    return report

def install(staged_path):
    package=ready()
    staged_path=Path(staged_path).resolve()
    if not staged_path.is_relative_to(HERE/'build/sessions') or staged_path.name!='stage.json':raise ValueError('staged evidence path')
    staged=json.loads(staged_path.read_text(encoding='utf-8'))
    if staged.get('staged') is not True or staged.get('allHandlesClosed') is not True or staged.get('failed') or staged.get('packageSha256')!=package['packageSha256']:
        raise RuntimeError('current complete staging required')
    session=transfer.Session('install')
    record_path=session.directory/'installation.json'
    state={'kind':'combined-factory-first-install','stage':'host-verified','completed':False,
           'packageSha256':package['packageSha256'],'stagedRecord':staged_path.relative_to(ROOT).as_posix(),
           'flashInstalled':False,'afInstalled':False,'afTimingActionsConnected':False,
           'replayBackendsInstalled':False,'controlsEnabled':False,'holdReleased':False,
           'shotsTriggered':0,'flashTrials':0,'automaticRetry':False,'automaticRestore':False}
    flash=capture.Loader()
    af=None;journal=None;final_io=None
    def save(phase):
        state['stage']=phase;state['linux']=session.summary()
        state['flashRequests']=flash.io.requests;state['flashWrites']=flash.io.writes
        state['flashHandlesClosed']=flash.io.closed
        if af is not None:
            state['afRequests']=af.io.requests;state['afWrites']=af.io.writes;state['afHandlesClosed']=af.io.closed
            state['afPhase']=af.phase
        if final_io is not None:
            state['finalReadOnlyRequests']=final_io.requests;state['finalReadOnlyWrites']=final_io.writes
            state['finalReadOnlyHandlesClosed']=final_io.closed
        record_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'stage':phase,'linuxRequests':state['linux']['requests'],'flashRequests':state['flashRequests'],
                          'afRequests':state.get('afRequests',0)}),flush=True)
    def health(label,minimum=180000):
        result=session.command(label,'/tmp/hbl-x1d-combined/system-check --require-held-min-ms '+str(minimum))
        if result['output'].strip()!=HEALTH:raise RuntimeError('combined health/pulse not confirmed')
    def phase(name):
        state['pendingPhase']=name;save(name+'-dispatch-intent')
        transfer.start(session,name)
        for index in range(90):
            time.sleep(1)
            outcome=transfer.poll(session,name)
            if outcome!='pending':break
            if index%15==14:print(json.dumps({'stage':name+'-pending'}),flush=True)
        else:raise RuntimeError('phase outcome unknown; do not repeat')
        state['phaseResult']=outcome
        if outcome.splitlines()!=['0',MARKERS[name]]:raise RuntimeError('phase failed: '+name)
        state['pendingPhase']=None;save(name+'-verified')
    save('host-verified')
    try:
        phase('preflight');phase('ui')
        health('before-current-farm-read')
        sys.path.insert(0,str(ROOT/'x1d/tools'))
        from farm_diagnostic_binary import FarmApplication
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        recovery=ROOT/'x1d/wireless-flash/build'/('formal-capture-recovery-combined-'+stamp+'.json')
        flash.prepare(FarmApplication().data,recovery)
        state['flashRecovery']=recovery.relative_to(ROOT).as_posix();save('factory-flash-baseline-verified')
        phase('observer')
        health('before-ram-first-write')
        session.command('ram-write-intent','r=/tmp/hbl-x1d-combined/install-state;umask 077;set -C;printf started >"$r/ram.started"')
        save('ram-write-intent-recorded')
        flash.probe();save('flash-cache-execution-and-restore-verified')
        health('before-flash-hooks')
        flash.install_disarmed();save('flash-hooks-disarmed-verified')
        health('before-flash-arm')
        state['flashInstalled']=None;save('flash-arm-intent')
        flash.arm();flash.verify(1)
        state['flashInstalled']=True;save('flash-installed-default-off')
        health('before-af-first-install')
        import settings_loader
        from settings_upgrade import FirstInstallContract, UpgradeLoader, UpgradeIO
        from r3_install_journal import InstallJournal
        from build_candidate import build
        from native_loader import failure
        contract=FirstInstallContract(nonce=secrets.randbelow(0xffffffff)+1)
        af=UpgradeLoader(contract,UpgradeIO(contract))
        af.preflight();save('af-factory-baseline-verified')
        recovery_dir=ROOT/'x1d/af-experiment/camera-settings-r1/recovery';recovery_dir.mkdir(exist_ok=True)
        af_path=recovery_dir/('settings-first-install-combined-'+stamp+'.json')
        journal=InstallJournal(af_path,contract.identity,backend='fixed_usb')
        af.attach(journal)
        af.persist(deliveryValidationSha256=hashlib.sha256(settings_loader.VALIDATION.read_bytes()).hexdigest())
        state['afRecovery']=af_path.relative_to(ROOT).as_posix();save('af-journal-ready')
        af.probe();save('af-cache-probe-verified')
        allocation,header=af.stage();save('af-original-allocation-verified')
        manifest,out=build(allocation[9])
        af.install(allocation,header,manifest,(out/'candidate.bin').read_bytes())
        journal.close();journal=None
        audit=InstallJournal.read_record(af_path,contract.identity)
        if (audit.get('installed') is not True or audit.get('phase')!='installed_settings_until_restart' or
            audit.get('inFlight') is not None or audit.get('cacheInFlight') is not None or audit.get('requiresReview') or
            audit.get('allHandlesClosed') is not True or audit['journalAudit'].get('incompleteTail')):raise RuntimeError('AF final journal not complete')
        state['afInstalled']=True;state['afJournalAudit']=audit['journalAudit'];save('af-first-install-verified')
        health('before-replay')
        phase('replay-prepare');phase('replay-config');phase('replay-jpeg')
        state['replayBackendsInstalled']=True
        phase('provider')
        health('before-final-controls')
        # AF与正式引闪未由后端/GUI阶段更改；最终只读核对代码和空闲状态。
        final_io=UpgradeIO(contract)
        state['finalReadOnlyVerification']=verify_after_services(contract,af.flash_sequence,final_io)
        flash.verify(1)
        save('final-device-code-and-idle-verified')
        phase('enable');state['controlsEnabled']=True
        phase('release');state['holdReleased']=True
        state['completed']=True;save('combined-installed-ready-for-user')
        return state
    except BaseException as error:
        state['lastCompletedStage']=state['stage'];state['errorClass']=type(error).__name__;state['failure']=str(error)
        if af is not None and journal is not None:
            from native_loader import failure
            failure(af,journal,error)
        save('stopped-review-before-further-action')
        raise
    finally:
        if journal is not None:journal.close()

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--install-staged':install(sys.argv[2])
    elif len(sys.argv)==1:
        report=ready();print(json.dumps({'hostReady':True,'packageSha256':report['packageSha256'],'hardwareRequests':0}))
    else:raise SystemExit('Unsupported arguments; no device requests')
