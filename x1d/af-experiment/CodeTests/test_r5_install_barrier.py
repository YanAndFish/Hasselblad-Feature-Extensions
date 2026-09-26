"""独立AF循环装载屏障的ARM执行与分阶段可见性模型。无USB接口。"""
import sys,json,struct,hashlib,unittest
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

BUILD=ROOT/'x1d/af-experiment/build/full-r5'
M=json.loads((BUILD/'manifest.json').read_text(encoding='utf-8'))
BASE=0x2b3f40;COUNT=0x2b3ff0;HOOK=0x19b960;LOOP=0x19d198;ORIGINAL=0x19b964

def branch(a,b):
    delta=b-a-8
    assert delta%4==0 and -(1<<25)<=delta<(1<<25)
    return 0xea000000|((delta>>2)&0xffffff)

def staging_blob():
    # 只写自有计数器。AF非idle时仍执行原事件流程，不能冻结正在运动的AF。
    # idle时原开始分发尚未执行；跳回原等待循环，取得任务已退出旧搜索栈的证据。
    words=[0xe92d000f,0xe10f2000,0,0xe5d01000,0xe3510000,0,
           0,0xe5901000,0xe2811001,0xe5801000,0xf57ff05b,
           0xe128f002,0xe8bd000f,0,
           0xe128f002,0xe8bd000f,0xe51b3094,0,
           0x6bb46c,COUNT,LOOP,ORIGINAL]
    def literal(index,reg,target):
        delta=BASE+target*4-(BASE+index*4+8)
        assert 0<=delta<4096
        words[index]=0xe59f0000|(reg<<12)|delta
    literal(2,0,18);literal(6,0,19);literal(13,15,20);literal(17,15,21)
    words[5]=(branch(BASE+5*4,BASE+14*4)&0x0fffffff)|0x10000000
    blob=struct.pack('<%dI'%len(words),*words)
    assert M['end']<=BASE and BASE+len(blob)<=COUNT and COUNT+4<=0x2b4000
    return blob

BLOB=staging_blob()

class BarrierCase:
    def __init__(self,farm,state=0,counter=0):
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.executed=[];self.writes=[]
        u.mem_map(0x100000,0x200000);u.mem_write(0x100000,farm.data)
        u.mem_map(0x6bb000,0x1000);u.mem_map(0x900000,0x10000)
        u.mem_write(BASE,BLOB);u.mem_write(COUNT,struct.pack('<I',counter))
        u.mem_write(HOOK,struct.pack('<I',branch(HOOK,BASE)))
        u.mem_write(0x6bb46c,bytes([state]))
        u.mem_write(0x90fd00-0x94,struct.pack('<I',0x20011))
        u.hook_add(UC_HOOK_CODE,self.code);u.hook_add(UC_HOOK_MEM_WRITE,self.write)
    def code(self,u,a,size,data):
        self.executed.append(a)
        if a in (LOOP,ORIGINAL):u.emu_stop();return
        if a!=HOOK and not BASE<=a<BASE+len(BLOB):raise AssertionError(hex(a))
    def write(self,u,access,a,size,value,data):
        assert (a==COUNT and size==4) or 0x90fcc0<=a and a+size<=0x90fd00
        self.writes.append((a,size,value))
    def run(self):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,0xa000001f)
        self.before={r:0x12000000+i for i,r in enumerate((UC_ARM_REG_R0,UC_ARM_REG_R1,
            UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R12,UC_ARM_REG_LR))}
        for r,v in self.before.items():u.reg_write(r,v)
        u.reg_write(UC_ARM_REG_SP,0x90fd00);u.reg_write(UC_ARM_REG_R11,0x90fd00)
        u.emu_start(HOOK,0,count=100)
        assert u.reg_read(UC_ARM_REG_SP)==0x90fd00 and u.reg_read(UC_ARM_REG_R11)==0x90fd00
        assert u.reg_read(UC_ARM_REG_CPSR)&0xf0000000==0xa0000000
        return u.reg_read(UC_ARM_REG_PC),struct.unpack('<I',u.mem_read(COUNT,4))[0]

class BarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.farm=FarmApplication()
        assert cls.farm.sha256==M['baseline_sha256']
        assert cls.farm.word(HOOK)==0xe51b3094 and cls.farm.word(LOOP)==branch(LOOP,0x19b718)

    def test_idle_ack_uses_no_candidate_or_overlay_code_and_preserves_registers(self):
        c=BarrierCase(self.farm);self.assertEqual(c.run(),(LOOP,1))
        for r,v in c.before.items():self.assertEqual(c.u.reg_read(r),v)
        self.assertEqual([a for a,size,v in c.writes if a==COUNT],[COUNT])

    def test_non_idle_does_not_ack_or_freeze_original_event_handling(self):
        for state in range(1,9):
            c=BarrierCase(self.farm,state=state);self.assertEqual(c.run(),(ORIGINAL,0))
            for r,v in c.before.items():
                self.assertEqual(c.u.reg_read(r),0x20011 if r==UC_ARM_REG_R3 else v)

    @classmethod
    def tearDownClass(cls):
        report={'artifactSha256':M['artifact_sha256'],'farmSha256':cls.farm.sha256,
            'helperBase':BASE,'helperEnd':BASE+len(BLOB),'counterAddress':COUNT,
            'helperSha256':hashlib.sha256(BLOB).hexdigest(),'helperHex':BLOB.hex(),
            'temporaryHook':[HOOK,cls.farm.word(HOOK),branch(HOOK,BASE)],
            'hardwareRequests':0,'hardwareLoaderImplemented':False,'installReady':False,
            'limitations':['独立屏障已运行原生ARM测试，未装入相机',
                '本程序仅独立屏障；普通诊断任务唤醒的离线验证见installation-task-wake.json',
                '尚未实现逐次USB写入与缓存失败的真实装载器测试',
                '未验证当前实时RTOS栈、用户输入及外部状态修改的并发条件']}
        (BUILD/'installation-barrier.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
