"""执行批量候选 ARM；外部 PHY/ROM 是替身，不证明实机射频时序。"""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'CodeTests'))
sys.path.insert(0,str(HERE/'research'))
from test_manual_power_candidate import Machine,D11,CONTEXT,render
import build_formal_firmware as builder

class BatchMachine(Machine):
    def __init__(self,blob):
        self.frames=[]
        self.fail_after=None
        super().__init__(blob)
    def write(self,u,access,address,size,value,data):
        if address==D11+0x492 and value==0x1802:
            self.frames.append(list(self.samples))
        super().write(u,access,address,size,value,data)
        if self.fail_after is not None and self.starts>=self.fail_after:
            self.setup_busy=True

def run():
    out=HERE/'build/batch-flash-candidate'
    manifest=json.loads((out/'firmware-build.json').read_text(encoding='utf-8'))
    blob=(out/'formal-wltest.bin').read_bytes()
    assert hashlib.sha256(blob).hexdigest()==manifest['sha256']
    for name,digest in manifest['sourceHashes'].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
    _,counts,lut,prefix=builder.power.inputs()
    m=BatchMachine(blob)
    assert m.invoke(0)==0x5855 and m.invoke(12002)==9 and not m.starts
    assert m.invoke(26)==1 and m.invoke(12000)==1
    indices=[g*82+(81 if g%2 else 40) for g in range(16)]
    for index in indices: assert m.invoke(16384+index)==1
    assert m.invoke(12002)==9 and m.starts==0 # 未提交不能发送
    assert m.invoke(12001)==1 and m.invoke(12003)==1
    assert m.invoke(12002)==1 and m.starts==16
    assert m.frames==[render(builder.runs(i,counts,prefix),lut) for i in indices]
    assert m.get(CONTEXT+12)==builder.FIRE_INDEX and m.get(CONTEXT+8)==1
    assert m.samples==render(builder.runs(builder.FIRE_INDEX,counts,prefix),lut)
    assert m.invoke(40)==1 and m.starts==17 # 短引闪仍单独一次
    assert len(m.frames[-1])==28416
    assert m.invoke(27)==1 and m.lock_depth==0 and m.invoke(12003)==0
    # 第二组硬件准备失败后停止，不能重发第一组或继续第三组。
    f=BatchMachine(blob);assert f.invoke(26)==1 and f.invoke(12000)==1
    for index in indices[:3]: assert f.invoke(16384+index)==1
    assert f.invoke(12001)==1;f.fail_after=1
    assert f.invoke(12002)==8 and f.starts==1 and f.get(CONTEXT+8)==0
    assert f.invoke(27)==1 and f.lock_depth==0
    # 空列表不发功率，但恢复短引闪；新事务不能沿用旧列表。
    z=BatchMachine(blob);assert z.invoke(26)==1 and z.invoke(12000)==1
    assert z.invoke(12001)==1 and z.invoke(12002)==1 and z.starts==0
    result={'passed':True,'firmwareSha256':manifest['sha256'],'sixteenFramesMatched':True,
            'offGroupsIncluded':True,'shortFlashSamples':28416,'failureStopsWithoutReplay':True,
            'hardwareRequests':0,'physicalTimingVerified':False,'installed':False}
    (out/'batch-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':run()
