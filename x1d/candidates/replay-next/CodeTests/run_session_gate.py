"""实际 ARM provider 的会话入口：缺少/拒绝守护器早退与上传前复查；GPU 为替身。"""
from pathlib import Path
import json
from run_provider import ProviderMachine,fixture,build_container,FALLBACK,TEXTURE_DELETE,sha
from arm_machine import HERE, X1D

class SessionMachine(ProviderMachine):
    def __init__(self,enabled=True,present=True,allowed=False):
        self.enabled,self.present,self.allowed=enabled,present,allowed
        self.admissions=[]
        super().__init__()
        self.admit_entry=self.callback('session-admit',self.admit)
    def admit(self):self.admissions.append(self.arg(0));self.ret(int(self.allowed))
    def shim(self,uc,at,size,context):
        name=self.entries[at]
        if name=='getenv' and self.cstring(self.arg(0))=='X1D_REPLAY_SESSION':self.ret(self.environment_one if self.enabled else 0)
        elif name=='dlsym' and self.cstring(self.arg(1))=='x1d_replay_session_admit':self.ret(self.admit_entry if self.present else 0)
        else:super().shim(uc,at,size,context)

def run():
    checks=[]
    for name,present in [('guard-missing',False),('guard-refuses',True)]:
        m=SessionMachine(present=present)
        before=len(m.reads);m.assert_fallback();assert len(m.reads)==before and not m.decodes
        checks.append(name+'-before-source-or-jpeg-read')
    dll=build_container()
    m=SessionMachine(allowed=True);m.select(fixture(dll));texture,_=m.request()
    assert texture!=FALLBACK and m.decodes==1
    create=next(name for name in m.native_symbols if 'Texture13createTexture' in name)
    assert m.call(create,[texture,123])==0x34567890 and m.admissions[-1]==1
    checks.append('allowed-worker-and-render-entry')
    m.allowed=False;before=len(m.gpu_images)
    assert m.call(create,[texture,123])==0 and len(m.gpu_images)==before
    checks.append('changed-render-context-refuses-before-qt-upload')
    m.call(TEXTURE_DELETE,[texture])
    sources=[Path(__file__),HERE/'native/replay_provider.cpp',HERE/'CodeTests/arm_machine.py',HERE/'CodeTests/run_provider.py']
    report={'passed':True,'checks':checks,'cameraAccess':False,'gpuExecuted':False,
            'moduleSha256':sha((HERE/'artifacts/adapter/libx1d-replay-provider.so').read_bytes()),
            'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in sources}}
    out=HERE/'artifacts/session-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'arm-gate.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'armSessionGateCases':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
