"""仅 AF 的串行实机协调；默认只离线核验，明确子命令才执行。"""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,json,secrets,shlex,sys,time
sys.dont_write_bytecode=True
import package
HERE=package.HERE;ROOT=package.ROOT;AF=package.AF
sys.path.insert(0,str(HERE.parent))
import transfer
REMOTE=transfer.REMOTE
MARKERS={'preflight':'af-only-preflight-ready','ui':'af-only-ui-ready','bus':'af-only-bus-ready',
         'release':'af-only-installed-ready-for-user','restore-linux':'af-only-original-linux-restored'}
def record(session,state,name):
    state.update(session.summary())
    (session.directory/name).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def phase(session,name):
    if name not in MARKERS or name in session.dispatched:raise ValueError('phase duplicate')
    session.dispatched.add(name)
    session.command(name+'-once','r='+REMOTE+';p='+name+';test ! -e "$r/phases/$p.sent" && (sh "$r/run.sh" "$p" >"$r/phases/$p.log" 2>&1) </dev/null >/dev/null 2>&1 &')
    for index in range(90):
        time.sleep(1)
        out=session.command(name+'-observe','r='+REMOTE+';p='+name+';if test -f "$r/phases/$p.exit";then cat "$r/phases/$p.exit";tail -n 1 "$r/phases/$p.log";else printf pending;fi')['output'].strip()
        if out!='pending':break
    else:raise RuntimeError('phase outcome unknown; do not repeat')
    if out.splitlines()!=['0',MARKERS[name]]:raise RuntimeError('phase '+name+' failed: '+out)
    print(json.dumps({'stage':name+'-verified'}),flush=True)
def stage():
    report,data=package.verify();session=transfer.Session('af-only-stage')
    state={'staged':False,'packageSha256':report['packageSha256'],'flashIncluded':False,'farmRequests':0}
    helper='''#!/bin/sh
set -eu
r=/tmp/hbl-x1d-combined
trap 'result=$?;echo "$result" >"$r/decode.exit"' 0
test ! -e "$r/af-only.tar.gz"
printf '%b' "$(/usr/bin/od -v -c "$r/p64" | /bin/sed 's/^[0-7]* *//' | awk -f "$r/d.awk")" >"$r/af-only.tar.gz"
sha256sum "$r/af-only.tar.gz" >"$r/decode.sha"
'''
    helper=';'.join(helper.splitlines()[1:])
    try:
        result=session.command('original-services','systemctl is-active victory-gui msg2dbus-farm')
        if result['output'].split()!=['active','active']:raise RuntimeError('original services not active')
        session.command('create-stage','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r" "$r/phases"')
        for name,body in [('d.awk',transfer.DECODER),('decode.sh',helper)]:
            for i,start in enumerate(range(0,len(body),70)):
                session.command(name+'-'+str(i),'printf %s '+shlex.quote(body[start:start+70])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        result=session.command('helper-hash','sha256sum '+REMOTE+'/decode.sh')
        if result['output'].split()[0]!=hashlib.sha256(helper.encode()).hexdigest():raise RuntimeError('helper checksum')
        encoded=base64.b64encode(data).decode()
        parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
        for i,part in enumerate(parts):
            session.command('chunk-'+str(i),'printf %s '+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if (i+1)%100==0:print(json.dumps({'stage':'af-transfer','chunks':i+1,'total':len(parts)}),flush=True)
        session.command('decode-once','r='+REMOTE+';(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        for i in range(90):
            time.sleep(1)
            out=session.command('decode-observe-'+str(i),'r='+REMOTE+';if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi')['output'].strip()
            if out!='pending':break
        else:raise RuntimeError('decode unknown; no retry')
        if out.split()[0:2]!=['0',report['packageSha256']]:raise RuntimeError('decode checksum mismatch')
        out=session.command('extract-once','cd '+REMOTE+' && tar xzf af-only.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf af-only-package-verified')['output']
        if out!='af-only-package-verified':raise RuntimeError('extract verification')
        state['staged']=True
    finally:
        record(session,state,'stage.json');print(json.dumps(state),flush=True)
    return session.directory/'stage.json'
def install(staged,previous=None):
    report,_=package.verify();staged=Path(staged).resolve()
    if not staged.is_relative_to(HERE.parent/'build/sessions') or staged.name!='stage.json':raise ValueError('stage path')
    evidence=json.loads(staged.read_text())
    if not evidence.get('staged') or evidence.get('failed') or not evidence.get('allHandlesClosed') or evidence['packageSha256']!=report['packageSha256']:raise ValueError('complete staging required')
    predecessor=None
    if previous is not None:
        previous=Path(previous).resolve()
        if not previous.is_relative_to(HERE.parent/'build/sessions') or previous.name!='installation.json':raise ValueError('previous evidence path')
        predecessor=json.loads(previous.read_text(encoding='utf-8'))
        if (predecessor.get('packageSha256')!=report['packageSha256'] or predecessor.get('failure')!='USB_READ' or
            predecessor.get('stage')!='stopped-review-no-retry' or predecessor.get('afPhase')!='preflight' or
            predecessor.get('afWrites')!=0 or not predecessor.get('afHandlesClosed') or not predecessor.get('allHandlesClosed') or
            predecessor.get('afInstalled') or predecessor.get('afRecovery') or predecessor.get('lastCompletedStage')!='bus-verified'):
            raise ValueError('only reviewed read-only USB failure can start a fresh transaction')
    session=transfer.Session('af-only-install')
    state={'completed':False,'packageSha256':report['packageSha256'],'stageEvidence':staged.relative_to(ROOT).as_posix(),
           'flashInstalled':False,'replayInstalled':False,'residentUiInstalled':False,'shots':0,'focusActions':0,'flashTrials':0}
    loader=None;journal=None
    def save(stage):
        state['stage']=stage
        if loader is not None:
            state.update(afPhase=loader.phase,afRequests=loader.io.requests,afWrites=loader.io.writes,afHandlesClosed=loader.io.closed,
                         lastAfOperation=getattr(loader.io,'last_operation',None),afHoldChecks=loader.io.hold_results)
        record(session,state,'installation.json');print(json.dumps({'stage':stage,'afRequests':state.get('afRequests',0)}),flush=True)
    try:
        if predecessor is None:
            for name in ('preflight','ui','bus'):
                save(name+'-dispatch-intent');phase(session,name);save(name+'-verified')
        else:
            state['reviewedReadOnlyPredecessor']=previous.relative_to(ROOT).as_posix()
            state['predecessorSha256']=package.sha(previous)
            save('fresh-readonly-transaction-review')
            out=session.command('same-linux-manifest','sha256sum '+REMOTE+'/manifest.sha256')['output']
            if out.split()[0]!=report['files']['manifest.sha256']:raise RuntimeError('running package changed')
            command='. '+REMOTE+'/common.sh;verify_package && owned && owned_dropins && absent "$s/ram.started" && absent "$s/hold.release" && gui_ready && bus_ready && printf af-resume-ready'
            out=session.command('existing-linux-held',command)['output']
            if out.splitlines()!=['system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1']*2+['af-resume-ready']:raise RuntimeError('original healthy window changed')
            save('bus-verified')
        sys.path.insert(0,str(AF))
        from af_only_bus_r2_loader import runtime as af_only_loader
        from af_only_install import AfOnlyContract,AfOnlyLoader,UpgradeIO
        from r3_install_journal import InstallJournal
        from build_candidate import build
        from native_loader import failure
        class AuditedIO(UpgradeIO):
            def transport(self,kind,a,v):
                self.last_operation={'kind':kind,'address':None if a is None else hex(a)}
                return super().transport(kind,a,v)
        contract=AfOnlyContract(nonce=secrets.randbelow(0xffffffff)+1)
        loader=AfOnlyLoader(contract,AuditedIO(contract));loader.preflight();save('factory-af-and-protected-regions-verified')
        directory=AF/'af-only-recovery';directory.mkdir(exist_ok=True)
        path=directory/('af-only-first-install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        journal=InstallJournal(path,contract.identity,backend='fixed_usb');loader.attach(journal)
        loader.persist(deliveryValidationSha256=package.sha(af_only_loader.VALIDATION))
        state['afRecovery']=path.relative_to(ROOT).as_posix();save('af-journal-ready')
        session.command('ram-write-intent','r='+REMOTE+'/install-state;umask 077;set -C;printf started >"$r/ram.started"')
        save('af-first-write-intent');loader.probe();save('af-cache-probe-verified')
        result,header=loader.stage();save('af-original-allocation-verified')
        manifest,out=build(result[9]);loader.install(result,header,manifest,(out/'candidate.bin').read_bytes())
        journal.close();journal=None
        audit=InstallJournal.read_record(path,contract.identity)
        if not audit.get('installed') or audit['phase']!='installed_settings_until_restart' or audit.get('inFlight') is not None or audit.get('cacheInFlight') is not None or audit.get('requiresReview') or not audit.get('allHandlesClosed') or audit['journalAudit'].get('incompleteTail'):raise RuntimeError('AF installation journal incomplete')
        state['afInstalled']=True;state['afJournalAudit']=audit['journalAudit'];save('af-install-verified')
        proof=package.sha(path)
        session.command('completed-af-proof','r='+REMOTE+'/install-state;umask 077;set -C;printf \'%s\\n\' '+proof+' >"$r/af-installed.sha256"')
        phase(session,'release');state['completed']=True;state['holdReleased']=True;save('af-only-installed-ready-for-user')
    except BaseException as error:
        state['failure']=str(error);state['lastCompletedStage']=state.get('stage')
        if hasattr(error,'win32'):state['win32']=error.win32
        if loader is not None and journal is not None:
            from native_loader import failure
            failure(loader,journal,error)
        save('stopped-review-no-retry');raise
    finally:
        if journal is not None:journal.close()
    return state
if __name__=='__main__':
    if sys.argv[1:]==['--stage']:stage()
    elif len(sys.argv)==3 and sys.argv[1]=='--install-staged':install(sys.argv[2])
    elif len(sys.argv)==3 and sys.argv[1]=='--resume-reviewed-readonly':
        previous=Path(sys.argv[2]);record=json.loads(previous.read_text(encoding='utf-8'))
        install(ROOT/record['stageEvidence'],previous)
    elif not sys.argv[1:]:
        r,_=package.verify();print(json.dumps({'ready':True,'bytes':r['bytes'],'hardwareRequests':0}))
    else:raise SystemExit('No action')
