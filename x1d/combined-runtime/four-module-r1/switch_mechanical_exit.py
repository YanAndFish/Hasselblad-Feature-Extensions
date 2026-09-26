"""机械触发改为退出空闲的独立工作副本；仅离线构建和检查。"""
from pathlib import Path
import hashlib,importlib.util,json,shutil,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE/'mechanical-start-hold';WORK=HERE/'mechanical-exit-idle'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def replace(path,a,b):
    text=path.read_text(encoding='utf-8');assert text.count(a)==1,(path,a)
    path.write_text(text.replace(a,b),encoding='utf-8',newline='\n')
def prepare():
    assert not WORK.exists()
    for folder,names in [('native',[p.name for p in (SOURCE/'native').iterdir() if p.is_file()]),
                         ('research',['build_formal_clients.py']),
                         ('CodeTests',['formal_policy.test.cpp','formal_policy_adapter.test.cpp','formal_policy_build.py','formal_radio_fake_platform.h']),
                         ('build/formal-flash-candidate',['formal_flash_hashes.h','formal_flash_lut.h'])]:
        d=WORK/folder;d.mkdir(parents=True)
        for n in names:shutil.copyfile(SOURCE/folder/n,d/n)
    replace(WORK/'native/formal_policy.h','formal_mechanical::rf_configure(&mechanical,1,2,delay);','formal_mechanical::rf_configure(&mechanical,1,3,delay);')
    replace(WORK/'CodeTests/formal_policy.test.cpp','HBL_MECH_CLOCK|3u|(4u<<8),0,4u','HBL_MECH_CLOCK|3u|(8u<<8),0,0u')
    replace(WORK/'CodeTests/formal_policy_adapter.test.cpp','HBL_MECH_CLOCK|3u|(4u<<8)|(done ? HBL_MECH_DONE:0u),0,4u','HBL_MECH_CLOCK|3u|(8u<<8)|(done ? HBL_MECH_DONE:0u),0,0u')
    replace(WORK/'CodeTests/formal_policy.test.cpp','        auto start=f.mech();at=f.step();CHECK(f.p.mechanicalSample(1,start,at*1000,f.step()));',
        '''        auto hold=f.mech();hold.clear_flags=HBL_MECH_CLOCK|3u|(4u<<8);hold.sync_status=4u;
        at=f.step();CHECK(!f.p.mechanicalSample(1,hold,at*1000,f.step()));CHECK(f.count(Policy::Fire)==0);
        auto start=f.mech();at=f.step();CHECK(f.p.mechanicalSample(1,start,at*1000,f.step()));''')
    return {'prepared':True,'hardwareRequests':0}
def test():
    m=load('exit_idle_tests',WORK/'CodeTests/formal_policy_build.py');m.ROOT=ROOT
    m.ZIG=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe';m.main()
def build():
    m=load('exit_idle_build',WORK/'research/build_formal_clients.py');m.ROOT=ROOT
    m.CACHE=ROOT/'.research-cache/x1d-1.25.0';m.BASELINE=m.CACHE/'baseline';return m.build()
def verify():
    changed=[p.name for p in (WORK/'native').iterdir() if p.is_file() and p.read_bytes()!=(SOURCE/'native'/p.name).read_bytes()]
    assert changed==['formal_policy.h']
    assert (SOURCE/'native/formal_policy.h').read_text(encoding='utf-8').replace('formal_mechanical::rf_configure(&mechanical,1,2,delay);','formal_mechanical::rf_configure(&mechanical,1,3,delay);')==(WORK/'native/formal_policy.h').read_text(encoding='utf-8')
    t=json.loads((WORK/'CodeTests/formal_policy_output/validation.json').read_text());b=json.loads((WORK/'build/formal-flash-program/client-build.json').read_text())
    assert t['passed'] and b['compiled']
    for r in (t,b):
        for n,h in r['sourceHashes'].items():assert hashlib.sha256((WORK/n).read_bytes()).hexdigest()==h,n
    observer=WORK/'build/formal-flash-program/libhbl-formal-observer.so';digest=hashlib.sha256(observer.read_bytes()).hexdigest()
    assert digest==b['outputs'][observer.name]['sha256']
    r={'passed':True,'sourceId':3,'mechanicalSource':'exit-idle','electronicPathUnchanged':True,'delayTableUnchanged':True,'checks':t['checks'],'observerSha256':digest,'observerBytes':observer.stat().st_size,'hardwareRequests':0,'installed':False}
    (WORK/'verification.json').write_text(json.dumps(r,indent=2)+'\n');return r
if __name__=='__main__':
    actions={'--prepare':prepare,'--test':test,'--build':build,'--verify':verify}
    assert len(sys.argv)==2 and sys.argv[1] in actions
    print(json.dumps(actions[sys.argv[1]]()))
