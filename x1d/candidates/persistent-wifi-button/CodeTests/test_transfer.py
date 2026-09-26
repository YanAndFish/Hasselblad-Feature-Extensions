from pathlib import Path
import base64,hashlib,importlib.util,json
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe_session',HERE/'session.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def main():
    report=json.loads((HERE/'build/current.json').read_text());data=Path(report['archive']).read_bytes()
    helper=m.load('probe_transfer_helper',m.ROOT/'x1d/candidates/ui-resident/session/delivery.py');helper.REMOTE=m.REMOTE
    class Model:
        def __init__(self,fail=None):self.calls=[];self.fail=fail
        def command(self,n,c):
            m.bounded(c);self.calls.append(n)
            if self.fail==n:raise RuntimeError('Simulated ambiguous response')
            if n=='services':o='active\n'*5
            elif n=='d.awk-hash':o=m.sha(helper.DECODER.encode())+' x'
            elif n=='decode.sh-hash':o=m.sha(helper.decoder_script().encode())+' x'
            elif n=='encoded-hash':o=m.sha(base64.b64encode(data))+' x'
            elif n.startswith('decode-observe'):o='0\n'+report['packageSha256']+' x'
            elif n=='extract-once':o='probe-package-verified'
            else:o=''
            return {'output':o}
    model=Model();assert m.transfer(model,report,data,lambda _:None)['staged']
    failed=Model('chunk-2')
    try:m.transfer(failed,report,data,lambda _:None)
    except RuntimeError:pass
    else:raise AssertionError('Ambiguous response ignored')
    assert failed.calls[-1]=='chunk-2' and 'decode-once' not in failed.calls
    result={'passed':True,'frames':len(model.calls),'packageSha256':report['packageSha256'],'sessionSha256':m.sha((HERE/'session.py').read_bytes()),'unknownResponseStops':True,'hardwareRequests':0}
    (HERE/'build/transfer-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'frames':len(model.calls)}))
if __name__=='__main__':main()
