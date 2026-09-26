"""新功率包全表交叉验证、真实候选 ARM 与固定参考灯接收路径；无硬件。"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/manual-power-candidate'
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
sys.path.insert(0,str(HERE/'research'))
import build_manual_power as build
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_INTR,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm

BASE=0x180000
PHY=0x300000
D11=0x400000
STACK=0x500000
RETURN=0x21fe00
STATE=0x2147e0
CONTEXT=0x217f00
RECEIVER_SHA='7eea75d17dea9d0ab8345ea4410148305ffb755b241132e3c5facd936a429dcb'


def render(runs,lut):
    samples=[0]*256
    phase=0
    for count,_,step in runs:
        for _ in range(count):
            phase=(phase+step)&0xffffffff
            samples.append(lut[phase>>22])
    return samples+[0]*0x31fc


class Machine:
    def __init__(self,blob):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        for start,size in ((BASE,0xa0000),(0x8000,0x1000),(PHY,0x2000),(D11,0x2000),(STACK,0x4000)):
            self.u.mem_map(start,size)
        self.u.mem_write(BASE,blob)
        self.put(PHY+0x100,D11)
        self.put(PHY+0x38,PHY+0x400)
        self.put(PHY+0x410,PHY+0x500)
        self.put(PHY+0x500,PHY+0x600)
        self.put(PHY+0x10e,0x1002,2)
        self.put(D11+0x492,2,2)
        self.put(D11+0x55a,0x1234,2)
        self.put(D11+0x55c,0x5678,2)
        self.samples=[0]*0x6f00
        self.port=0
        self.lock_depth=0
        self.starts=0
        self.sample_reads=0
        self.sample_writes=0
        self.tsf_reads=0
        self.tamper=False
        self.setup_busy=False
        self.calls=[]
        self.min_sp=STACK+0x3f00
        self.psm_writes=[]
        self.external={0x1cc670:'lock',0x1cc67c:'unlock',0x1c620e:'readPhy',
                       0x1bb31c:'carrier',0x1bb3d6:'sampleSetup',0x8710:'delay',
                       0x1bb210:'sampleStop',0x1c6224:'writePhy'}
        # 外部 RTOS/PHY 函数用 SVC + BX LR 替身；候选内部不用代码/基本块回调。
        # 旧试验区只在模拟内改成 UDF 陷阱，进入即失败；生产候选字节不改。
        for address in self.external:
            self.u.mem_write(address,b'\x00\xdf\x70\x47')
        self.u.mem_write(0x216000,b'\x00\xde'*(0x800//2))
        self.u.hook_add(UC_HOOK_INTR,self.interrupt)
        # 读取替身只覆盖外设区；不在候选的条件数据读取中插入 Python 回调。
        self.u.hook_add(UC_HOOK_MEM_READ,self.read,begin=D11,end=D11+0x1fff)
        self.u.hook_add(UC_HOOK_MEM_WRITE,self.write,begin=D11,end=D11+0x1fff)
        self.u.hook_add(UC_HOOK_MEM_WRITE,self.write,begin=STACK,end=STACK+0x3fff)

    def put(self,address,value,size=4):
        self.u.mem_write(address,int(value).to_bytes(size,'little'))

    def get(self,address,size=4):
        return int.from_bytes(self.u.mem_read(address,size),'little')

    def interrupt(self,u,number,_):
        address=u.reg_read(arm.UC_ARM_REG_PC)-2
        assert number==2 and address in self.external, ('非外部替身异常',number,hex(address))
        name=self.external[address]
        args=[u.reg_read(reg) for reg in (arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,
                                         arm.UC_ARM_REG_R2,arm.UC_ARM_REG_R3)]
        self.calls.append((name,args))
        answer=0
        if name=='lock':
            self.lock_depth+=1
        elif name=='unlock':
            self.lock_depth-=1
            assert self.lock_depth>=0
        elif name=='readPhy':
            answer=3 if args[1]==0x471 else int(self.setup_busy) if args[1]==0x403 else 0
        u.reg_write(arm.UC_ARM_REG_R0,answer)

    def read(self,u,access,address,size,value,_):
        if address==D11+0x134:
            if self.tamper and self.sample_reads==0:
                self.samples[300]^=1
            index=(self.port-0x24000)//4
            assert size==4 and 0<=index<len(self.samples)
            self.put(address,self.samples[index])
            self.port+=4
            self.sample_reads+=1
        elif address==D11+0x180:
            self.tsf_reads+=1

    def write(self,u,access,address,size,value,_):
        if STACK<=address<STACK+0x4000:
            self.min_sp=min(self.min_sp,address)
        if address==D11+0x130:
            assert size==4
            self.port=value
        elif address==D11+0x134:
            index=(self.port-0x24000)//4
            assert size==4 and 0<=index<len(self.samples)
            self.samples[index]=value
            self.port+=4
            self.sample_writes+=1
        elif address==D11+0x492:
            self.psm_writes.append(value)
            if value==0x1802:
                self.starts+=1

    def invoke(self,selector,pi=PHY):
        self.u.reg_write(arm.UC_ARM_REG_CPSR,0x3f)
        self.u.reg_write(arm.UC_ARM_REG_R0,pi)
        self.u.reg_write(arm.UC_ARM_REG_R1,selector)
        self.u.reg_write(arm.UC_ARM_REG_SP,STACK+0x3f00)
        self.u.reg_write(arm.UC_ARM_REG_LR,RETURN|1)
        self.u.emu_start(0x214401,RETURN,timeout=5000000)
        assert self.u.reg_read(arm.UC_ARM_REG_PC)==RETURN
        assert self.u.reg_read(arm.UC_ARM_REG_SP)==STACK+0x3f00
        return self.u.reg_read(arm.UC_ARM_REG_R0)


def receiver_check(frames):
    firmware=(HERE/'build/receiver-reference/AD400pro_V1.50.bin').read_bytes()
    assert hashlib.sha256(firmware).hexdigest()==RECEIVER_SHA
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    u.mem_map(0,0x20000)
    u.mem_write(0x3000,firmware)
    u.mem_map(0x20000000,0x10000)
    stop=0x1f000
    writes=[]
    def code(cpu,address,size,_):
        if address==stop:
            cpu.emu_stop()
        elif not (0xc134<=address<0xc478 or 0xdef6<=address<0xdf10):
            raise AssertionError(('非功率接收路径',hex(address)))
    def write(cpu,access,address,size,value,_):
        assert 0x20000000<=address<0x20010000
        if address<0x2000e000:
            writes.append((address,size,value))
    u.hook_add(UC_HOOK_CODE,code)
    u.hook_add(UC_HOOK_MEM_WRITE,write)
    for frame in frames:
        command=frame[8:]
        assert command[0]==0xa9 and command[2]==0xbc
        u.mem_write(0x20000000,bytes(0x1000))
        u.mem_write(0x20000123,command[1:2])
        u.mem_write(0x20000132,b'\x01')
        u.mem_write(0x20000133,b'\xfe')
        writes.clear()
        u.reg_write(arm.UC_ARM_REG_SP,0x2000fff0)
        u.reg_write(arm.UC_ARM_REG_LR,stop|1)
        for reg,value in zip((arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2),command[1:]):
            u.reg_write(reg,value)
        u.emu_start(0xc135,stop+2,count=1000)
        assert u.reg_read(arm.UC_ARM_REG_PC)==stop
        assert u.mem_read(0x20000133,1)[0]==command[3]
        assert u.mem_read(0x20000132,1)[0]==1
        assert writes==[(0x20000133,1,command[3])]
    return len(frames)


def check():
    assert Path.cwd().resolve()==ROOT
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    blob=(OUT/'manual-power-wltest.bin').read_bytes()
    assert hashlib.sha256(blob).hexdigest()==manifest['sha256']
    for path,digest in manifest['sourceHashes'].items():
        assert hashlib.sha256((HERE/path).read_bytes()).hexdigest()==digest,path
    baseline,counts,lut,prefix=build.inputs()
    expected=json.loads((OUT/'expected-hashes.json').read_text(encoding='ascii'))
    assert hashlib.sha256((OUT/'expected-hashes.json').read_bytes()).hexdigest()==manifest['expectedHashesSha256']
    lutpath=OUT/'reference-lut.bin'
    lutpath.write_bytes(struct.pack('<1024I',*lut))
    source=HERE/'CodeTests/godox_power_wave.test.c'
    exe=OUT/'godox_power_wave.test.exe'
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        env[key]=str(OUT/name)
    subprocess.run([str(compiler),'cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(exe)],
                   env=env,check=True,capture_output=True,timeout=60)
    vectors=subprocess.run([str(exe),str(lutpath)],check=True,capture_output=True,text=True,timeout=30).stdout.splitlines()
    assert len(vectors)==405
    frames=[]
    for index,line in enumerate(vectors):
        framehex,checksum=line.split()
        frame=bytes.fromhex(framehex)
        assert frame==prefix+bytes((0xa9,0x0a+index//81,0xbc,index%81))
        assert int(checksum,16)==expected[index]
        frames.append(frame)
    receiver_cases=receiver_check(frames)
    print('405 组功率波形与参考灯接收分支通过。',flush=True)

    cases=[]
    m=Machine(blob)
    assert m.invoke(0)==0x5852
    assert m.invoke(48)==9 and m.starts==0
    allowed={0,15,16,17,18,26,27,48}
    for selector in list(set(range(512))-allowed)+[917,0xffff,0xffffffff]:
        assert m.invoke(selector)==0xfffd
    assert not m.calls and not m.sample_writes and not m.starts
    cases.append('initial-and-old-selector-rejection')
    m.put(STATE+16,1)
    assert m.invoke(26)==9 and m.invoke(27)==9
    assert m.lock_depth==0 and not m.calls
    cases.append('foreign-hold-rejection')

    tested=[(0,0),(0,80),(1,17),(1,80),(2,30),(2,80),(3,0),(3,20),(3,47),(3,80),(4,0),(4,80)]
    max_stack=0
    for group,value in tested:
        m=Machine(blob)
        assert m.invoke(26)==1 and m.invoke(26)==1 and m.lock_depth==1
        index=group*81+value
        assert m.invoke(512+index)==1
        assert m.starts==0 and m.lock_depth==1
        runs=build.power_runs(group,value,counts,prefix)
        assert bytes(m.u.mem_read(build.RUN_ADDRESS,768))==b''.join(struct.pack('<HHI',*run) for run in runs)
        assert m.samples==render(runs,lut)
        assert m.sample_reads==0x6f00 and m.sample_writes==0x6f00
        assert m.get(STATE+4)==expected[index]
        assert m.invoke(15)|(m.invoke(16)<<16)==expected[index]
        assert m.invoke(17)==1 and m.invoke(18)==index
        before_io=(m.sample_reads,m.sample_writes)
        for shot in range(2):
            assert m.invoke(48)==1 and m.starts==shot+1
            assert (m.sample_reads,m.sample_writes)==before_io
            assert m.get(D11+0x492,2)==2
            assert m.get(D11+0x55a,2)==0x1234 and m.get(D11+0x55c,2)==0x5678
        assert [args[0] for name,args in m.calls if name=='delay']==[500,500]
        assert m.tsf_reads==0
        assert m.invoke(27)==1 and m.lock_depth==0
        assert m.invoke(48)==9 and m.invoke(512+index)==9 and m.starts==2
        max_stack=max(max_stack,STACK+0x3f00-m.min_sp)
        cases.append(f'generate-hash-send-release-{group}-{value}')
    print('12 组真实 ARM 生成、全样本读回、单次发送与释放通过。',flush=True)

    def prepared():
        cpu=Machine(blob)
        assert cpu.invoke(26)==1 and cpu.invoke(512+3*81+47)==1
        return cpu

    for name,address,value in [('hash',STATE+4,0),('expected',CONTEXT+16,0),
                               ('index',CONTEXT+12,405),('generated',STATE,0),
                               ('verified',STATE+8,0),('not-ready',CONTEXT+8,0)]:
        m=prepared()
        m.put(address,value)
        assert m.invoke(48)==3 and m.starts==0
        assert m.invoke(27)==1 and m.lock_depth==0
        cases.append('reject-'+name)
    for name,address,value,result in [('channel',PHY+0x10e,0x1001,4),
                                     ('mac',D11+0x120,1,5),('high',D11+0x538,1,6),
                                     ('psm',D11+0x492,0,7)]:
        m=prepared()
        m.put(address,value,4 if name=='mac' else 2)
        assert m.invoke(48)==result and m.starts==0 and m.get(CONTEXT+8)==0
        assert m.invoke(27)==1 and m.lock_depth==0
        cases.append('reject-'+name)
    m=prepared()
    m.setup_busy=True
    assert m.invoke(48)==8 and m.starts==0 and m.get(D11+0x492,2)==2
    assert [args[1] for name,args in m.calls if name=='carrier']==[1,0]
    assert m.invoke(27)==1 and m.lock_depth==0
    cases.append('sample-setup-busy-cleanup')

    m=Machine(blob)
    assert m.invoke(26)==1
    m.tamper=True
    assert m.invoke(512+3*81+47)==13
    assert m.get(STATE)==0 and m.get(STATE+8)==0 and m.get(CONTEXT+8)==0
    assert m.invoke(48)==3 and m.starts==0
    assert m.invoke(27)==1 and m.lock_depth==0
    cases.append('sample-readback-corruption')
    m=Machine(blob)
    assert m.invoke(26)==1
    m.put(D11+0x120,1)
    assert m.invoke(512)==2 and not m.sample_writes and not m.starts
    assert m.invoke(27)==1 and m.lock_depth==0
    cases.append('generation-mac-busy')
    m=prepared()
    original=bytes(m.u.mem_read(CONTEXT,28))
    for selector in (26,27,48,512):
        assert m.invoke(selector,PHY+0x1000)==9
    assert bytes(m.u.mem_read(CONTEXT,28))==original and not m.starts
    m.put(CONTEXT+20,1)
    for selector in (26,27,48,512):
        assert m.invoke(selector)==9
    assert not m.starts
    m.put(CONTEXT+20,0)
    assert m.invoke(27)==1 and m.lock_depth==0
    cases.append('owner-and-inflight-rejection')
    report={'passed':True,'candidateSha256':manifest['sha256'],'compiledWaveformVectors':405,
            'referenceReceiverSha256':RECEIVER_SHA,'referenceReceiverCases':receiver_cases,
            'armCases':cases,'armCaseCount':len(cases),'largestObservedStackBytes':max_stack,
            'stackObservation':'lowest-address-written-not-per-instruction-SP-sampling',
            'instructionHooks':'none-in-candidate; external-SVC-stubs-and-legacy-UDF-fence',
            'realCandidateInstructions':True,'originalGeneratorAndHashInstructions':True,
            'externalPhyAndRtosCallsModeled':True,'ordinaryFlashReceiverPathReached':False,
            'hardwareRequests':0,'installed':False,'lampReceptionVerified':False,
            'sourceHashes':{str(path.relative_to(HERE)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (Path(__file__),source,HERE/'native/godox_power_wave.h',HERE/'firmware/manual_power.c')}}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('passed','compiledWaveformVectors','referenceReceiverCases','armCaseCount',
                                              'largestObservedStackBytes','hardwareRequests','installed')},ensure_ascii=False))


if __name__=='__main__':
    check()
