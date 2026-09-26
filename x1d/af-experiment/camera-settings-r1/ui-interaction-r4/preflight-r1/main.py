"""只继续已记录的 r4 GUI preflight 61 失败；不覆盖旧阶段。"""
import argparse,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import continuation_package as package
import micro_stage
import transfer

def predecessor(path):
    p=Path(path).resolve()
    if not p.is_relative_to(package.PARENT/'build/sessions') or p.name!='result.json':raise ValueError('r4 failed apply evidence required')
    value=package.read(p)
    if (value.get('action')!='apply' or value.get('completed') or value.get('phaseResult')!='61\nsystem-active-hold-not-ready'
            or value.get('packageSha256')!='0448c022ed474effc5130b3c541cf95a75c05cbf1dffea2f9ee7f5bb1c53435e'
            or value.get('afRamWrites')!=0 or value.get('busRestarted') is not False
            or value.get('failed') or not value.get('allHandlesClosed')):raise ValueError('exact completed no-mutation preflight failure required')
    staged=(package.ROOT/value['sourceStage']).resolve()
    if not staged.is_relative_to(package.PARENT/'build/sessions') or staged.name!='stage.json':raise ValueError('old stage identity')
    original=package.read(staged)
    if not original.get('staged') or original.get('failed') or not original.get('allHandlesClosed') or original.get('packageSha256')!=value['packageSha256']:raise ValueError('old complete stage required')
    return p,value

def execute(evidence,restore=False):
    report,_=package.verify();prior,old=predecessor(evidence)
    s=transfer.Session('af-ui-r4-preflight-r1-'+('restore' if restore else 'continue'))
    d=transfer.REMOTE;phase='restore-preflight-r1' if restore else 'apply-preflight-r1'
    state={'completed':False,'phase':phase,'priorEvidence':prior.relative_to(package.ROOT).as_posix(),'priorSha256':package.sha(prior),'afRamWrites':0,'busRestarted':False}
    try:
        # All original phase files are retained and hash-checked before the new phase.
        expected=package.read(package.HERE/'expected.json')
        for files in ('apply.sent apply.exit','apply.log'):
            out=s.command('prior-evidence','cd '+d+'/phases && sha256sum '+files)['output']
            for line in out.splitlines():
                digest,name=line.split()
                if name not in expected or digest!=expected[name]:raise ValueError('old phase evidence changed')
            if len(out.splitlines())!=len(files.split()):raise ValueError('incomplete prior evidence')
        if not restore:
            s.command('untouched-gui', 'd='+d+';test ! -e "$d/touched" && test ! -e "$d/applied" && test ! -e "$d/failure-restored" && test ! -e "$d/failure-restore-unknown" && test ! -e "$d/restored"')
            micro_stage.stage()
        output=s.command('same-continuation','sha256sum '+d+'/preflight-r1/manifest.sha256')['output']
        if output.split()[0]!=report['files']['manifest.sha256']:raise ValueError('continuation package mismatch')
        s.command('new-phase-once','d='+d+';p='+phase+';test ! -e "$d/phases/$p.sent" && (sh "$d/preflight-r1/run.sh" "$p" >"$d/phases/$p.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        for _ in range(60):
            time.sleep(1)
            output=s.command('new-phase-observe','d='+d+';p='+phase+';if test -f "$d/phases/$p.exit";then cat "$d/phases/$p.exit";tail -n 1 "$d/phases/$p.log";else printf pending;fi')['output'].strip()
            if output!='pending':break
        else:raise RuntimeError('new GUI phase outcome unknown; do not repeat')
        state['phaseResult']=output
        marker='af-ui-r4-previous-af-gui-restored' if restore else 'af-ui-r4-ready'
        if output.splitlines()!=['0',marker]:raise RuntimeError('new GUI phase failed; preserve all evidence')
        state['completed']=True
    except BaseException as error:
        state.update(error=str(error),win32=getattr(error,'win32',None));raise
    finally:micro_stage.record(s,state,'result.json')
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('report','continue','restore'),nargs='?',default='report');p.add_argument('--evidence');a=p.parse_args()
    if a.action=='report':r,_=package.verify();result=dict(r,offlineReady=True)
    else:
        if not a.evidence:p.error('--evidence required')
        result=execute(a.evidence,a.action=='restore')
    print(json.dumps(result,ensure_ascii=False,indent=2))
