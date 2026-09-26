"""为明确恢复完成且从未写入 AF 的失败阶段保留原目录，供独立下一轮装载。"""
import hashlib,shlex,sys
from pathlib import Path
sys.dont_write_bytecode=True
import session
SCRIPT=';'.join([
    '. /tmp/hbl-x1d-combined/common.sh',
    'verify_package && owned && owned_dropins || exit 60',
    'regular "$s/linux-restored.done" && absent "$s/ram.started" && absent "$gui" && absent "$farm" || exit 61',
    'clean_service victory-gui && clean_service msg2dbus-farm && private "$a" || exit 62',
    'q=/tmp/hbl-af-only-before-bus-fix',
    'absent "$q" || exit 63',
    'mv "$r" "$q"',
    'mv "$a" "$q/previous-af-runtime"',
    'printf af-only-restored-stage-preserved'])
def run():
    s=session.transfer.Session('af-only-preserve-restored-stage')
    state={'preserved':False,'ramWrites':0,'destination':'/tmp/hbl-af-only-before-bus-fix'}
    try:
        for i,start in enumerate(range(0,len(SCRIPT),70)):
            s.command('helper-'+str(i),'printf %s '+shlex.quote(SCRIPT[start:start+70])+(' >' if i==0 else ' >>')+session.REMOTE+'/preserve.sh')
        r=s.command('helper-hash','sha256sum '+session.REMOTE+'/preserve.sh')
        if r['output'].split()[0]!=hashlib.sha256(SCRIPT.encode()).hexdigest():raise RuntimeError('helper checksum')
        out=s.command('preserve-once','sh '+session.REMOTE+'/preserve.sh')['output']
        if out!='af-only-restored-stage-preserved':raise RuntimeError('preserve failed')
        state['preserved']=True
    finally:
        session.record(s,state,'preserved.json');print(state)
if __name__=='__main__':
    if sys.argv[1:]==['--preserve-restored']:run()
    elif not sys.argv[1:]:print({'hardwareRequests':0,'helperSha256':hashlib.sha256(SCRIPT.encode()).hexdigest()})
    else:raise SystemExit('No action')
