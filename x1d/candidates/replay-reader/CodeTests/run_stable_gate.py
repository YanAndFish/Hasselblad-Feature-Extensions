"""ARM 会话准入：拒绝时不读 JPEG/RAW，不执行 GL 上传。"""
import json
from pathlib import Path
from run_stable_provider import StableMachine,image,CREATE
from run_provider import sha,TEXTURE_DELETE
from arm_machine import HERE,X1D
class Gated(StableMachine):
    def __init__(self,present=True):
        self.present=present;self.allowed=False;self.admissions=[]
        super().__init__();self.admit_entry=self.callback('admit-session',self.admit)
    def admit(self):self.admissions.append(self.arg(0));self.ret(self.allowed)
    def shim(self,uc,at,size,context):
        name=self.entries[at]
        if name=='getenv' and self.cstring(self.arg(0))=='X1D_REPLAY_SESSION':self.ret(self.environment_one)
        elif name=='dlsym' and self.cstring(self.arg(1))=='x1d_replay_session_admit':self.ret(self.admit_entry if self.present else 0)
        else:super().shim(uc,at,size,context)
def run():
    cases=[]
    for present in [False,True]:
        m=Gated(present);m.select_files(image());assert m.request()[0]==0 and not m.reads and not m.fallback_calls
        cases.append('missing-guard' if not present else 'denied-guard')
    m.allowed=True;t,size=m.request('fullsize');assert t and m.permits==0
    m.allowed=False;assert m.call(CREATE,[t,1])==0 and not m.gl_names
    m.call(TEXTURE_DELETE,[t]);assert m.permits==1;cases.append('guard-change-before-upload')
    report={'passed':True,'cases':cases,'cameraAccess':False,'gpuExecuted':False,'moduleSha256':sha((HERE/'artifacts/adapter/libx1d-replay-provider.so').read_bytes()),
        'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'CodeTests/run_stable_provider.py',HERE/'native/replay_provider.cpp']}}
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True);(out/'gate.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':True,'cases':len(cases)}))
if __name__=='__main__':run()
