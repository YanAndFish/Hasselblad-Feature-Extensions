"""只在组合模块工作副本中修正机械触发源；原始独立包保持不变。"""
from pathlib import Path
import hashlib,importlib.util,json,shutil,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];FLASH=ROOT/'x1d/wireless-flash'
WORK=HERE/'mechanical-start-hold';OUT=WORK/'build/formal-flash-program'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def prepare():
    if WORK.exists():raise ValueError('preserve existing correction workspace')
    (WORK/'native').mkdir(parents=True)
    for p in (FLASH/'native').iterdir():
        if p.is_file() and p.suffix in ('.h','.c','.cpp','.S'):shutil.copyfile(p,WORK/'native'/p.name)
    (WORK/'research').mkdir();shutil.copyfile(FLASH/'research/build_formal_clients.py',WORK/'research/build_formal_clients.py')
    (WORK/'build/formal-flash-candidate').mkdir(parents=True)
    for name in ('formal_flash_hashes.h','formal_flash_lut.h'):
        shutil.copyfile(FLASH/'build/formal-flash-candidate'/name,WORK/'build/formal-flash-candidate'/name)
    tests=WORK/'CodeTests';tests.mkdir()
    for name in ('formal_policy.test.cpp','formal_policy_adapter.test.cpp','formal_policy_build.py','formal_radio_fake_platform.h'):
        shutil.copyfile(FLASH/'CodeTests'/name,tests/name)
    policy=WORK/'native/formal_policy.h';text=policy.read_text(encoding='utf-8')
    old='formal_mechanical::rf_configure(&mechanical,1,1,delay);'
    assert text.count(old)==1
    policy.write_text(text.replace(old,'formal_mechanical::rf_configure(&mechanical,1,2,delay);'),encoding='utf-8',newline='\n')
    test=tests/'formal_policy.test.cpp';text=test.read_text(encoding='utf-8')
    old='HBL_MECH_CLOCK|2u|(2u<<8),0,HBL_MECH_B'
    assert text.count(old)==1
    text=text.replace(old,'HBL_MECH_CLOCK|3u|(4u<<8),0,4u')
    # 复用完整状态机测试，额外独立核对事件选择而非仅替换全部输入。
    entry='int main() {'
    assert text.count(entry)==1
    extra='''static void mechanical_source_regression() {
    const unsigned exposures[]={250000,8000,4000};
    for(unsigned exposure:exposures) {
        Fixture f;f.update(0,1,40);f.options(true);f.drain();CHECK(f.flush(1,exposure,false));f.drain();f.ack(1,FORMAL_OK);
        auto b=f.mech();b.clear_flags=HBL_MECH_CLOCK|2u|(2u<<8);b.sync_status=HBL_MECH_B;
        uint64_t at=f.step();CHECK(!f.p.mechanicalSample(1,b,at*1000,f.step()));CHECK(f.count(Policy::Fire)==0);
        auto start=f.mech();at=f.step();CHECK(f.p.mechanicalSample(1,start,at*1000,f.step()));
        auto command=f.next();CHECK(command.action==Policy::Fire);CHECK(command.deadlineUs==at+5000);
        f.finish(Policy::Fire);CHECK(!f.p.mechanicalSample(1,start,f.step()*1000,f.step()));
    }
}
'''
    text=text.replace(entry,extra+entry+'\n    mechanical_source_regression();')
    test.write_text(text,encoding='utf-8',newline='\n')
    adapter=tests/'formal_policy_adapter.test.cpp';text=adapter.read_text(encoding='utf-8')
    old='HBL_MECH_CLOCK|2u|(2u<<8)|(done ? HBL_MECH_DONE:0u),0,HBL_MECH_B'
    assert text.count(old)==1
    adapter.write_text(text.replace(old,'HBL_MECH_CLOCK|3u|(4u<<8)|(done ? HBL_MECH_DONE:0u),0,4u'),encoding='utf-8',newline='\n')
    return {'prepared':True,'mechanicalSource':'startup-hold-rising','sourceId':2,'delayTableUnchanged':True,'electronicPathUnchanged':True,'hardwareRequests':0}
def test():
    b=load('mechanical_source_policy_tests',WORK/'CodeTests/formal_policy_build.py')
    b.ROOT=ROOT;b.ZIG=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe';b.main()
def build():
    b=load('mechanical_source_clients',WORK/'research/build_formal_clients.py');b.ROOT=ROOT;b.CACHE=ROOT/'.research-cache/x1d-1.25.0';b.BASELINE=b.CACHE/'baseline'
    result=b.build()
    proof={'compiled':True,'mechanicalSource':'startup-hold-rising','sourceId':2,'delayTableUnchanged':True,'electronicPathUnchanged':True,
           'observerSha256':hashlib.sha256((OUT/'libhbl-formal-observer.so').read_bytes()).hexdigest(),'hardwareRequests':0,'installed':False}
    (WORK/'correction.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
def verify():
    changed=[]
    for p in (WORK/'native').iterdir():
        if not p.is_file():continue
        original=(FLASH/'native'/p.name).read_bytes()
        if original!=p.read_bytes():changed.append(p.name)
    assert changed==['formal_policy.h']
    original=(FLASH/'native/formal_policy.h').read_text(encoding='utf-8')
    assert original.replace('formal_mechanical::rf_configure(&mechanical,1,1,delay);','formal_mechanical::rf_configure(&mechanical,1,2,delay);')==(WORK/'native/formal_policy.h').read_text(encoding='utf-8')
    tests=json.loads((WORK/'CodeTests/formal_policy_output/validation.json').read_text())
    native=json.loads((OUT/'client-build.json').read_text())
    assert tests['passed'] and tests['checks']==6983 and native['compiled']
    for report in (tests,native):
        for name,digest in report['sourceHashes'].items():
            assert hashlib.sha256((WORK/name).read_bytes()).hexdigest()==digest,name
    assert native['outputs']['libhbl-formal-observer.so']['sha256']==hashlib.sha256((OUT/'libhbl-formal-observer.so').read_bytes()).hexdigest()
    proof={'passed':True,'nativeChanges':changed,'onlyMechanicalSourceChanged':True,'electronicPathUnchanged':True,'delayTableUnchanged':True,'checks':6983,'hardwareRequests':0}
    (WORK/'verification.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
if __name__=='__main__':
    if sys.argv[1:]==['--prepare']:print(json.dumps(prepare()))
    elif sys.argv[1:]==['--test']:test()
    elif sys.argv[1:]==['--build']:print(json.dumps(build()))
    elif sys.argv[1:]==['--verify']:print(json.dumps(verify()))
    else:raise SystemExit('explicit offline action required')
