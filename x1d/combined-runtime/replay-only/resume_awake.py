"""明确稳定待机、前段结束后，以原厂GUI服务启动恢复安装窗口。"""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
import baseline_delta as delta

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--install-staged': raise SystemExit('No action')
    evidence=Path(sys.argv[2]).resolve()
    delta.OUT=delta.HERE/'build/runtime-maps-r4'
    report,_=delta.verify_delta()
    delta.runner.require_repaired_package(report)
    record=json.loads(evidence.read_text(encoding='utf-8'))
    if not record.get('staged') or record.get('failed') or not record.get('allHandlesClosed') or record['packageSha256']!=report['packageSha256']:
        raise ValueError('Complete staged package required')
    s=delta.runner.root_transfer.Session('replay-only-awake-window')
    d=delta.runner.REMOTE
    outcome={'ready':False,'wholeCameraReboot':False,'guiRestarts':0,'farmRequests':0}
    try:
        s.command('prior-phase-ended',f'r={d};test "$(cat "$r/ui-r4.exit")" = 64 && test ! -e "$r/state" && test ! -e "$r/ui-r5.sent"')
        observed=s.command('stable-standby',f'{d}/read-health --require-ui-stage')['output'].strip()
        if observed!='system=4 suc=0 farm=0 pwr=0 ui-power=1 hold=0': raise RuntimeError('Expected stable standby changed')
        outcome['before']=observed
        outcome['guiRestartIntent']=True
        s.command('original-gui-start-once','systemctl restart victory-gui')
        outcome['guiRestarts']=1
        out=s.command('active-after-gui-start',f'{d}/read-health --require-active')['output'].strip()
        if out!='system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0': raise RuntimeError('Active not confirmed')
        outcome['after']=out;outcome['ready']=True
        print(json.dumps({'stage':'original-ui-active'}),flush=True)
    except BaseException as error:
        outcome['failure']=str(error);raise
    finally:
        delta.runner.save(s,outcome,'awake.json');print(json.dumps(outcome),flush=True)
    delta.NEXT_PHASE='ui-r5'
    delta.runner.verify_package=delta.verify_delta
    delta.runner.StreamingTransfer=delta.NewPhaseTransfer
    delta.runner.install(evidence)
