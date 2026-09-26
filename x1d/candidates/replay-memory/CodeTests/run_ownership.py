"""执行固定原 Qt ARM QByteArray 所有权/COW；宿主分配器替身，不运行相机进程。"""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/candidates/replay-reader/CodeTests'))
from run_stable_provider import StableMachine
def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    m=StableMachine();cases=[];empty=m.byte_array(b'');source=m.byte_array(b'synthetic-jpeg-bytes')
    held=m.byte_array(b'');assign='_ZN10QByteArrayaSERKS_';old=m.word(source)
    m.call(assign,[held,source]);assert m.word(held)==old and m.word(old)==2
    cases.append('owned-copy-shares-compressed-allocation')
    m.call(assign,[source,empty]);assert m.word(old)==1 and m.array(held)==b'synthetic-jpeg-bytes' and old in m.live
    cases.append('original-array-release-does-not-release-held-bytes')
    m.call(assign,[source,held]);add=m.allocate(1);m.uc.mem_write(add,b'!')
    m.call('_ZN10QByteArray6appendEPKci',[source,add,1])
    assert m.word(source)!=old and m.array(held)==b'synthetic-jpeg-bytes' and m.array(source)==b'synthetic-jpeg-bytes!'
    cases.append('subsequent-source-mutation-detaches')
    m.call(assign,[held,empty]);assert old not in m.live
    cases.append('last-held-reference-release-frees-allocation')
    raw=m.allocate(5);m.uc.mem_write(raw,b'raw!!');view=m.allocate(4)
    m.call('_ZN10QByteArray11fromRawDataEPKci',[view,raw,5]);assert m.word(m.word(view)+8)&0x7fffffff==0
    m.call(assign,[held,view]);m.uc.mem_write(raw,b'new!!')
    d=m.word(held);assert bytes(m.uc.mem_read((d+m.word(d+12))&0xffffffff,5))==b'new!!'
    cases.append('fromRawData-remains-alias-and-must-be-rejected')
    report={'passed':True,'cameraAccess':False,'realArm':['Qt QByteArray assignment/fromRawData/append/reallocation/refcount'],
      'replaced':['libc allocation and memory boundaries'],'cases':cases,'moduleHashes':m.module_hashes,
      'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),
       ROOT/'x1d/candidates/replay-reader/CodeTests/arm_machine.py',ROOT/'x1d/candidates/replay-reader/CodeTests/run_stable_provider.py',
       ROOT/'x1d/candidates/replay-reader/CodeTests/run_provider.py']}}
    out=HERE/'artifacts/ownership';out.mkdir(parents=True,exist_ok=True)
    (out/'execution.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ownershipCases':len(cases),'cameraAccess':False}))
if __name__=='__main__':run()
