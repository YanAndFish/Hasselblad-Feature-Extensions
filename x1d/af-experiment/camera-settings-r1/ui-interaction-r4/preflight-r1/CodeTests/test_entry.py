"""Bounded command framing for the tiny continuation and guarded new phase."""
import base64,hashlib,importlib.util,json,shlex,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import continuation_package as package
import micro_stage
spec=importlib.util.spec_from_file_location('reviewed_entry',HERE/'main.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
def run():
    report=package.read(HERE/'build/package.json');blob=(HERE/'build/continuation.tar.gz').read_bytes()
    output=HERE/'CodeTests/output';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as directory:
        class Fake:
            def __init__(self,name):self.directory=Path(directory);self.calls=[];self.failed=False
            def summary(self):return {'allHandlesClosed':True,'failed':False,'requests':len(self.calls)}
            def command(self,label,command,timeout_ms=15000):
                assert 0<len(command.encode('ascii'))<=231 and '\n' not in command and '\0' not in command,(label,len(command))
                self.calls.append((label,command))
                if label=='original-services':out='active\nactive'
                elif label=='helper-hash':
                    body=''.join(shlex.split(c.split('printf %s ',1)[1])[0] for l,c in self.calls if l.startswith('decode.sh-'))
                    out=hashlib.sha256(body.encode()).hexdigest()+'  helper'
                elif label.startswith('decode-observe'):out='0\n'+report['packageSha256']+'  archive'
                elif label=='extract-once':
                    encoded=''.join(shlex.split(c.split('printf %s ',1)[1])[0] for l,c in self.calls if l.startswith('chunk-'))
                    assert base64.b64decode(encoded)==blob
                    out='af-ui-r4-package-verified'
                elif label=='prior-evidence':
                    names=command.split('sha256sum ',1)[1].split();expected=package.read(HERE/'expected.json');out='\n'.join(expected[n]+'  '+n for n in names)
                elif label=='same-continuation':out=report['files']['manifest.sha256']+'  manifest.sha256'
                elif label=='new-phase-observe':out='0\naf-ui-r4-ready'
                else:out=''
                return {'output':out,'closed':True,'exit_code':0}
        with patch.object(package,'verify',return_value=(report,blob)),patch.object(micro_stage.transfer,'Session',Fake),patch.object(micro_stage.time,'sleep'):
            micro_stage.stage()
            predecessor=package.PARENT/'build/sessions/af-ui-r4-apply-20260912T173356108139Z/result.json'
            with patch.object(micro_stage,'stage',return_value=Path(directory)/'stage.json'):
                assert entry.execute(predecessor)['completed']
    result={'passed':True,'maximumFrameBytes':231,'microArchiveRoundtrip':True,'newPhaseFraming':True,'hardwareRequests':0}
    (output/'entry.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':run()
