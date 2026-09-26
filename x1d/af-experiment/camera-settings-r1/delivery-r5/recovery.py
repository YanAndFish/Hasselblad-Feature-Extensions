"""明确分支恢复；未知 RAM 写入只保留证据，不自动重试。"""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import delivery_package as package
from runtime import Trace, TracedIO
from rollback import AfOnlyRollbackContract, AfOnlyRollbackLoader
from r3_install_journal import InstallJournal
from native_loader import failure
from session import phase, record
import transfer
HERE, ROOT, REMOTE = package.HERE, package.ROOT, transfer.REMOTE

def installation(path):
    path = Path(path).resolve()
    if not path.is_relative_to(HERE/'build/sessions') or path.name != 'installation.json':
        raise ValueError('r3 installation evidence required')
    return path, package.read(path)

def inspect(path):
    path, state = installation(path)
    trace_path = path.parent/'af-trace.jsonl'
    trace = Trace.inspect(trace_path) if trace_path.is_file() else None
    result = {'hardwareRequests': 0, 'stage': state.get('stage'), 'afPhase': state.get('afPhase'),
        'afWrites': state.get('afWrites'), 'nextAction': 'stop-and-review', 'automaticRetry': False}
    if (trace is None and state.get('afPreflightStarted') is False and state.get('afWrites')==0
            and state.get('afRequests')==0 and not state.get('afRecovery') and not state.get('afInstalled')
            and state.get('allHandlesClosed')):
        phases=state.get('linuxPhases',{})
        if phases and all(v.get('state')=='observed' and isinstance(v.get('exitCode'),int) for v in phases.values()):
            result['nextAction']='restore-preflight-linux' if ('ui' in phases or 'bus' in phases) else 'no-linux-service-changes'
    if trace:
        events = trace['events']
        result.update(traceTailComplete=trace['completeTail'], traceEvents=len(events),
            lastOperation=events[-1], traceSha256=trace['lastSha256'])
        no_writes = (trace['completeTail'] and len(events)>1 and events[-1]['event']=='result'
            and events[-1]['allHandlesClosed'] and all(e.get('writes',0)==0 and e.get('kind')!='write' for e in events))
        if (no_writes and state.get('afWrites')==0 and state.get('afHandlesClosed')
                and state.get('afPhase')=='preflight' and not state.get('afRecovery')
                and state.get('allHandlesClosed') and not state.get('afInstalled')):
            result['nextAction'] = 'restore-preflight-linux'
    if state.get('afRecovery'):
        jp = (ROOT/state['afRecovery']).resolve()
        if not jp.is_relative_to(HERE/'recovery'):
            raise ValueError('foreign recovery journal')
        audit = InstallJournal.read_record(jp, package.read(jp)['artifactSha256'])
        result['journal'] = {'phase':audit['phase'], 'inFlight':audit.get('inFlight'),
            'cacheInFlight':audit.get('cacheInFlight'), 'audit':audit['journalAudit']}
        if (audit.get('installed') and audit['phase']=='installed_settings_until_restart'
                and not audit['journalAudit']['incompleteTail'] and audit.get('inFlight') is None
                and audit.get('cacheInFlight') is None and not audit.get('requiresReview')
                and audit.get('allHandlesClosed')):
            result['nextAction'] = 'rollback-held-or-user-restart-after-release'
    return result

def restore_preflight(path):
    report, _ = package.verify()
    path, state = installation(path)
    if state.get('packageSha256') != report['packageSha256'] or inspect(path)['nextAction'] != 'restore-preflight-linux':
        raise ValueError('verified read-only preflight failure required')
    session = transfer.Session('af-r3-restore-preflight')
    result = {'completed':False, 'sourceEvidence':path.relative_to(ROOT).as_posix(), 'afWrites':0}
    try:
        expected = report['files']['manifest.sha256']
        out = session.command('same-package', 'sha256sum '+REMOTE+'/manifest.sha256')['output']
        if out.split()[0] != expected:
            raise ValueError('running package changed')
        session.command('no-ram-start', '. '+REMOTE+'/common.sh;restore_before_ram_ready && printf ready')
        phase(session, 'restore-linux')
        result['completed'] = True
    finally:
        record(session,result,'recovery.json')
    return result

def rollback_held(path):
    report, _ = package.verify()
    path = Path(path).resolve()
    c = AfOnlyRollbackContract.from_journal(path)
    source = c.source_record
    if (source.get('transportPolicySha256') != package.sha(HERE/'runtime.py')
            or source.get('deliveryValidationSha256') != package.sha(HERE/'validation.json')
            or source.get('requiresReview') or source['journalAudit']['incompleteTail']):
        raise ValueError('complete r3 source journal required')
    session = transfer.Session('af-r3-rollback-held')
    result = {'completed':False, 'sourceJournal':path.relative_to(ROOT).as_posix()}
    trace = Trace(session.directory/'af-trace.jsonl',c.identity)
    loader = AfOnlyRollbackLoader(c,TracedIO(c,trace))
    journal = None
    try:
        # Existing held window only. A released/expired window is never recreated here.
        out = session.command('same-package', 'sha256sum '+REMOTE+'/manifest.sha256')['output']
        if out.split()[0] != report['files']['manifest.sha256']:
            raise ValueError('running package changed')
        session.command('existing-held-window', '. '+REMOTE+'/common.sh;verify_package && owned && owned_dropins && absent "$s/hold.release" && gui_ready && bus_ready')
        loader.preflight()
        jp = HERE/'recovery'/('rollback-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        journal = InstallJournal(jp,c.identity,backend='fixed_usb')
        loader.attach(journal)
        result['recoveryJournal'] = jp.relative_to(ROOT).as_posix()
        loader.persist(sourceJournalSha256=package.sha(path), sourceJournalAudit=source['journalAudit'],
            transportPolicySha256=package.sha(HERE/'runtime.py'))
        loader.probe();loader.stage();loader.restore()
        journal.close();journal=None
        audit = InstallJournal.read_record(jp,c.identity)
        if (audit.get('phase')!='rolled_back_until_restart' or not audit.get('rolledBack')
                or audit.get('inFlight') is not None or audit.get('cacheInFlight') is not None
                or audit['journalAudit']['incompleteTail'] or not audit.get('allHandlesClosed')):
            raise RuntimeError('rollback not verified')
        result.update(afRestored=True, journalAudit=audit['journalAudit'])
        proof = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
        session.command('ram-restored-proof','r='+REMOTE+'/install-state;umask 077;set -C;printf \'%s\\n\' '+proof+' >"$r/ram-restored.sha256"')
        phase(session,'restore-linux')
        result['completed']=True
    except BaseException as error:
        if journal is not None:
            failure(loader,journal,error)
        result.update(error=str(error),win32=getattr(error,'win32',None))
        raise
    finally:
        result.update(afPhase=loader.phase,afWrites=loader.io.writes,afRequests=loader.io.requests,
            afHandlesClosed=loader.io.closed,lastAfOperation=loader.io.last_operation)
        if journal is not None:journal.close()
        trace.close()
        record(session,result,'recovery.json')
    return result
