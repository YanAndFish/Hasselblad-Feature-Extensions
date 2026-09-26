"""仅收尾本次已写完、主机只读白名单拒绝的事务；不重传主体。"""
import json,hashlib,sys
from datetime import datetime
from pathlib import Path
from temporary_install import HERE,ROOT,runtime,TemporaryLoader,InstallJournal,failure

def finish():
    p=HERE/'recovery/temporary-release-20260914-000604.json'
    identity='8d38b810ed20edf9f080fa4ed646847e9678cb2bb7385286b398047bf0091728'
    r=InstallJournal.read_record(p,identity)
    trace=runtime.Trace.inspect(p.with_suffix('.trace.jsonl'))
    last=trace['events'][-1]
    if (not trace['completeTail'] or r['journalAudit']['incompleteTail'] or
        r['phase']!='verifying_gated' or r.get('inFlight') or r.get('cacheInFlight') or
        not r['allHandlesClosed'] or last['address']!='0x2adc20' or
        last['error']!='fixed read denied' or last['transport'] or r['writeRequests']!=1428):
        raise RuntimeError('reviewed stop differs')
    c=runtime.AfOnlyContract(nonce=r['bootstrapNonce'],profile='release')
    m=r['candidate'];folder=HERE/'build/release'/format(m['base'],'08x')
    c.bind(r['allocationResponse'],(0,r['allocationResponse'][10]|0x80000000),m,(folder/'candidate.bin').read_bytes())
    c.scratch_before=r['scratchBefore']
    c.identity=runtime.old.digest({'prior':identity,'finish':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                 'contract':c.identity})
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    target=HERE/'recovery'/('temporary-finish-'+stamp+'.json')
    t=runtime.Trace(target.with_suffix('.trace.jsonl'),c.identity)
    io=runtime.TracedIO(c,t);l=TemporaryLoader(c,io);j=InstallJournal(target,c.identity,backend='fixed_usb')
    l.journal=j;io.journal=j;l.probe_executed=True;l.gated=True
    # 之前所有 sync 已完成且无未知操作；再次同步后才声明本次 cache 已验证。
    try:
        l.phase_to('verifying_gated')
        l.persist(priorJournal=str(p.relative_to(ROOT)),priorAudit=r['journalAudit'],candidate=m,
                  guiHoldRequired=False,installed=False)
        old=runtime.old
        for a,v in ((c.control,0),(old.GATE_HOOK,c.bootstrap_hooks[old.GATE_HOOK][1]),
                    (old.WAKE_HOOK,c.bootstrap_hooks[old.WAKE_HOOK][0]),(old.CB,old.ORIG_CB),(old.ARG,old.ORIG_ARG)):
            if io.read(a)!=v:raise RuntimeError('current gated state differs')
        if [io.read(c.request+4*i) for i in range(13)]!=r['allocationResponse']:
            raise RuntimeError('allocation changed')
        for a in c.allocation_header_addresses(r['allocationResponse']):
            if io.read(a)!=(0 if a==r['allocationResponse'][8]-8 else r['allocationResponse'][10]|0x80000000):
                raise RuntimeError('allocation header differs')
        l.idle();l.quiescent()
        l.sync(m['base'],m['end']-m['base'])
        for a,_,v in m['emulatorOnlyHooks']:
            if io.read(a)!=v:raise RuntimeError('installed hook differs')
            l.sync_hook(a)
        l.verify();l.idle();l.hold_boundary('before-release',park=True)
        l.phase_to('releasing_native_gate');l.write(c.control,2)
        l.write(old.GATE_HOOK,c.bootstrap_hooks[old.GATE_HOOK][0]);l.sync_hook(old.GATE_HOOK)
        l.phase_to('restoring_cache_slot');l.quiet();l.write(old.ARG,old.ORIG_ARG);l.write(old.CB,old.ORIG_CB);l.quiescent()
        for a,v in ((old.GATE_HOOK,c.bootstrap_hooks[old.GATE_HOOK][0]),
                    (old.WAKE_HOOK,c.bootstrap_hooks[old.WAKE_HOOK][0]),(old.CB,old.ORIG_CB),(old.ARG,old.ORIG_ARG)):
            if io.read(a)!=v:raise RuntimeError('final restoration differs')
        l.verify_flash();l.idle();l.phase_to('installed_settings_until_restart')
        l.persist(phase=l.phase,installed=True,allHandlesClosed=io.closed,temporaryRam=True,
                  requests=io.requests,writeRequests=io.writes,restartRemoves=True)
        print(json.dumps({'installed':True,'allHandlesClosed':io.closed,'journal':str(target),'writes':io.writes}),flush=True)
    except BaseException as e:
        failure(l,j,e);raise
    finally:j.close();t.close()

if __name__=='__main__':
    if sys.argv[1:]!=['finish-reviewed-stop']:raise SystemExit('explicit finish-reviewed-stop required')
    finish()
