"""审查只读诊断候选的 ARM 产物、字段覆盖与无状态改变边界。"""
from pathlib import Path
import importlib.util,io,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('replay_health_diag_build',HERE/'session/build_health_diagnostic.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def run():
    assert Path.cwd().resolve()==ROOT
    report=json.loads((HERE/'build/session/diagnostic/build.json').read_text(encoding='utf-8'));source=(HERE/'session/native/health_diagnostic.cpp').read_text(encoding='utf-8')
    binary=ROOT/report['binary'];checks=[]
    def check(n,v):assert v,n;checks.append(n)
    check('actual ARM diagnostic bound to source',report['compiled'] and report['binarySha256']==m.base.sha(binary) and report['sourceSha256']==m.base.sha(HERE/'session/native/health_diagnostic.cpp'))
    sys.path.insert(0,str(m.CACHE/'python'));from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(binary.read_bytes()));check('ARM32 executable',elf.elfclass==32 and elf['e_machine']=='EM_ARM')
    check('only Qt DBus Core and fixed runtime dependencies',report['needed']==['libQt5DBus.so.5','libQt5Core.so.5','libstdc++.so.6','libgcc_s.so.1','libdl.so.2','libc.so.6','libpthread.so.0'])
    check('five exact read-only fields labelled',all(v in source for v in ('system_state','suc.status','farm.status','pwrctrl.status','ui.power')))
    check('three samples and pid stability diagnosed','sample<=3' in source and 'ui-pid-changed' in source)
    check('timeout is bounded and diagnosed','alarm(8)' in source and 'reason=timeout' in source)
    check('DBus calls prohibit auto-start','setAutoStartService(false)' in source)
    check('only Properties Get method is constructed','QStringLiteral("Get")' in source and 'createMethodCall' in source and all(v not in source for v in ('SetProperty','QStringLiteral("Set")','WriteFile','Trigger','Capture')))
    check('failure reports values without device identity','reason=not-ready system=%d suc=%d farm=%d pwr=%d power=%d pid=%u' in source and all(v not in source.lower() for v in ('serialnumber','filename','photo')))
    check('success preserves health contract with measured final values','replay-health-ready pid=%u system=%d power=%d' in source and 'previous,last.system,last.power' in source)
    check('candidate remains outside frozen package',not report['includedInFrozenPackage'])
    proof={'passed':True,'checks':checks,'binarySha256':report['binarySha256'],'sourceSha256':report['sourceSha256'],
        'testSha256':m.base.sha(Path(__file__)),'hardwareRequests':0,'targetValidated':False}
    m.base.save(HERE/'build/session/diagnostic-validation.json',proof);print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
