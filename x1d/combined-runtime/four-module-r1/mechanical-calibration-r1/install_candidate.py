"""检查离线证据并只读核对现有 RAM，再执行获授权的成对增量。"""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import increment
session=increment.session
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit():
    af=session.inspect_af.run(True)
    class ReadOnly(session.capture.FixedIO):
        def exchange(self,kind,a=None,v=None):
            if kind!='read':raise RuntimeError('read-only preservation audit')
            return super().exchange(kind,a,v)
    loader=session.capture.Loader(ReadOnly());loader.verify(1)
    assert af['passed'] and loader.io.writes==0 and loader.io.closed
    return {'af':af,'flashRequests':loader.io.requests,'flashWrites':loader.io.writes,'allFlashHandlesClosed':loader.io.closed}
if __name__=='__main__':
    assert sys.argv[1:]==['--install']
    transaction=json.loads((HERE/'CodeTests/increment-transaction-validation.json').read_text())
    assert transaction['passed'] and transaction['applySha256']==sha(HERE/'apply.sh')
    policy=json.loads((HERE/'CodeTests/formal_policy_output/validation.json').read_text())
    assert policy['passed']
    for name,digest in policy['sourceHashes'].items():assert sha(HERE/name)==digest,name
    for name in ('validation.json','native-validation.json'):
        assert json.loads((HERE/'CodeTests/calibration-ui-output'/name).read_text())['passed']
    assert json.loads((HERE/'CodeTests/evf-hint-output/validation.json').read_text())['durationMs']==2000
    before=audit();(HERE/'update/preservation-before.json').write_text(json.dumps(before,indent=2)+'\n')
    print(json.dumps({'stage':'existing-af-and-flash-verified'}),flush=True)
    result=increment.install()
    after=audit();(HERE/'update/preservation-after.json').write_text(json.dumps(after,indent=2)+'\n')
    result['afAndFlashPreserved']=True
    (HERE/'update/final-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'installed':True,'afAndFlashPreserved':True,'temporaryOnly':True}),flush=True)
