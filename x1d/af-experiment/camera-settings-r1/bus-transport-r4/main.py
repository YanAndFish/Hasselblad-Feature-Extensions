"""独立 AF bus 修复；report 离线，stage/apply/restore 由主任务独占执行。"""
import argparse,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
import bus_package as package
import stage,transfer

def action(name,evidence):
    if name not in ('apply','restore'):raise ValueError('bus action')
    report,_=package.verify();path=Path(evidence).resolve()
    if not path.is_relative_to(package.HERE/'build/sessions') or path.name!='stage.json':raise ValueError('this bus stage evidence required')
    previous=package.read(path)
    if not previous.get('staged') or previous.get('failed') or not previous.get('allHandlesClosed') or previous['packageSha256']!=report['packageSha256']:raise ValueError('complete matching bus stage required')
    session=transfer.Session('af-bus-r4-'+name);d=transfer.REMOTE
    result={'action':name,'completed':False,'packageSha256':report['packageSha256'],'afRamWrites':0,'busRestartMayOccur':True,'guiChanged':False,'sourceStage':path.relative_to(package.ROOT).as_posix()}
    try:
        output=session.command('same-bus-package','sha256sum '+d+'/manifest.sha256')['output']
        if output.split()[0]!=report['files']['manifest.sha256']:raise ValueError('staged bus manifest changed')
        session.command(name+'-once','d='+d+';p='+name+';test ! -e "$d/phases/$p.sent" && (sh "$d/run.sh" "$p" >"$d/phases/$p.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        for _ in range(60):
            time.sleep(1)
            output=session.command(name+'-observe','d='+d+';p='+name+';if test -f "$d/phases/$p.exit";then cat "$d/phases/$p.exit";tail -n 1 "$d/phases/$p.log";else printf pending;fi')['output'].strip()
            if output!='pending':break
        else:raise RuntimeError('bus phase outcome unknown; do not repeat')
        marker='af-bus-r4-ready' if name=='apply' else 'af-bus-r4-previous-bus-restored'
        result['phaseResult']=output
        if output.splitlines()!=['0',marker]:raise RuntimeError('bus phase failed; inspect phase log and failure-restore markers')
        result['completed']=True
    except BaseException as error:
        result.update(error=str(error),win32=getattr(error,'win32',None));raise
    finally:stage.record(session,result,'result.json')
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('report','stage','apply','restore'),nargs='?',default='report');p.add_argument('--evidence');a=p.parse_args()
    if a.action=='report':r,_=package.verify();result=dict(r,offlineReady=True,physicalRoundtripVerified=False,requiresInstalledDeliveryR5=True)
    elif a.action=='stage':result={'stageEvidence':str(stage.stage())}
    else:
        if not a.evidence:p.error('--evidence required')
        result=action(a.action,a.evidence)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
