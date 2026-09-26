"""完整引闪+AF 观察安装后的单次收尾；不修改给 AF 绑定的原成功记录。"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import sys
import time
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import formal_install_session as flash
HERE,ROOT,OUT=flash.HERE,flash.ROOT,flash.OUT
AF_RECOVERY=ROOT/'x1d/af-experiment/recovery'
HEALTH='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1'

def load_af(path):
    path=Path(path).resolve()
    if path.parent!=AF_RECOVERY.resolve() or not path.name.startswith('native-observe-') or path.suffix!='.json':
        raise RuntimeError('Expected this batch AF observation journal')
    sys.path.insert(0,str(ROOT/'x1d/af-experiment'))
    from r3_install_journal import InstallJournal
    anchor=json.loads(path.read_text(encoding='utf-8'))
    record=InstallJournal.read_record(path,anchor['artifactSha256'])
    required={'phase':'installed_observation_until_restart','installed':True,'backend':'fixed_usb',
              'mode':'native_af_observation','ownedCodeExecuted':True,'predictionActuation':False,
              'speedOverrides':False,'nativeFinePreserved':True,'flashCodePreserved':True,'allHandlesClosed':True}
    if any(record.get(k)!=v or type(record.get(k)) is not type(v) for k,v in required.items()):
        raise RuntimeError('AF observation installation not completely verified')
    audit=record.get('journalAudit',{})
    if record.get('inFlight') is not None or record.get('cacheInFlight') is not None or record.get('requiresReview') or audit.get('format')!=2 or audit.get('incompleteTail') or not audit.get('verifiedEvents'):
        raise RuntimeError('AF event chain incomplete or a transaction is still in flight')
    return record

def finish(installation_path,af_path):
    package=flash.check_host()
    path=Path(installation_path).resolve()
    if path.parent!=OUT.resolve() or not path.name.startswith('installation-') or path.suffix!='.json':
        raise RuntimeError('Expected current fixed flash success record')
    installed=json.loads(path.read_text(encoding='utf-8'))
    expected={'installed':True,'allHandlesClosed':True,'farmArmed':True,'installationGateReleased':False,
              'installationHoldRetained':True,'stage':'installed-default-off-locked-for-joint-af'}
    if installed.get('packageSha256')!=package['packageSha256'] or any(installed.get(k)!=v or type(installed.get(k)) is not type(v) for k,v in expected.items()):
        raise RuntimeError('Flash installation is not this completed locked batch')
    af=load_af(af_path)
    preserved=af.get('preservedFlash',{})
    if preserved.get('sourceInstallation')!=path.relative_to(ROOT).as_posix() or preserved.get('installationSha256')!=hashlib.sha256(path.read_bytes()).hexdigest() or preserved.get('packageSha256')!=package['packageSha256']:
        raise RuntimeError('AF record belongs to a different flash installation')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    record_path=OUT/('joint-completion-'+stamp+'.json')
    if record_path.exists():raise RuntimeError('Joint completion record already exists')
    session=flash.transfer.Session('joint-completion-session-'+stamp+'.json')
    state={'completed':False,'stage':'inputs-verified','flashInstallation':path.name,
           'flashInstallationSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
           'afJournal':str(Path(af_path).resolve().relative_to(ROOT)).replace('\\','/'),
           'afJournalAudit':af['journalAudit'],'packageSha256':package['packageSha256'],
           'userControlsReleased':False,'holdReleased':False,'predictionActuation':False,
           'automaticRetry':False,'cameraShotsTriggered':0,'agentFlashTrials':0,
           'sessionRecord':session.output.name}
    def save(stage):
        state['stage']=stage
        state['linuxRequests']=sum(e['submitted'] for e in session.entries)
        state['allHandlesClosed']=all(e['closed'] for e in session.entries)
        record_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def health(label,option='--require-held-min-ms 10000'):
        result=session.command(label,'/tmp/hbl-wireless-flash/formal-system-check '+option)
        if result['output'].strip()!=(HEALTH if option.startswith('--require-held') else HEALTH[:-1]+'0'):
            raise RuntimeError('Joint completion health/hold verification failed')
    save('inputs-verified')
    try:
        health('joint-before-controls')
        result=session.command('joint-default-off','d=/tmp/hbl-wireless-flash;head -n 2 "$d/formal-worker.status";test ! -e "$d/formal-enable.ready" && test ! -L "$d/formal-enable.ready" && test ! -e "$d/formal-enable.confirmed"')
        lines=result['output'].splitlines()
        if len(lines)!=2 or lines[0]!='formal-worker-ready-default-off' or not lines[1].startswith('master=0 radio-held=0 radio-busy=0 same-process=1 pid='):
            raise RuntimeError('Worker is not default off with controls locked')
        state['userControlsReleased']=None;save('control-enable-attempt-unknown-until-reply')
        result=session.command('joint-enable-once','d=/tmp/hbl-wireless-flash;umask 077;set -C;printf ready >"$d/formal-enable.ready" && printf requested')
        if result['output']!='requested':raise RuntimeError('Control enable request not confirmed; do not repeat')
        for _ in range(20):
            time.sleep(0.2)
            result=session.command('joint-enable-confirmation','d=/tmp/hbl-wireless-flash;if test -f "$d/formal-enable.confirmed";then cat "$d/formal-enable.confirmed";else printf pending;fi')
            if result['output']!='pending':break
        else:raise RuntimeError('Control enable not acknowledged; no automatic retry')
        if result['output'].strip()!='ready':raise RuntimeError('Control enable acknowledgement mismatch')
        state['userControlsReleased']=True;save('controls-released-default-off')
        health('joint-before-hold-release','--require-held')
        state['holdReleased']=None;save('hold-release-attempt-unknown-until-reply')
        session.command('joint-release-hold-once','umask 077;set -C;printf release >/tmp/hbl-wireless-flash/formal-state/hold.release')
        state['holdReleased']=True
        time.sleep(0.6)
        health('joint-final-health','--require-active')
        state['completed']=True;save('joint-installed-default-off-ready-for-user')
        return state
    except Exception as error:
        state['lastCompletedStage']=state['stage'];state['failure']=str(error)
        save('stopped-review-joint-record-before-any-next-action')
        raise

def offline_ready():
    proof=json.loads((HERE/'CodeTests/formal_joint_output/validation.json').read_text(encoding='utf-8'))
    return proof.get('passed') is True and all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in proof['sourceHashes'].items())

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--finish':
        if not offline_ready():raise RuntimeError('Current joint completion checks required; no device requests')
        print(json.dumps(finish(sys.argv[2],sys.argv[3]),ensure_ascii=False))
    elif len(sys.argv)==1:
        print(json.dumps({'offlineReady':offline_ready(),'hardwareRequests':0}))
    else:raise SystemExit('Unsupported arguments; no device requests')
