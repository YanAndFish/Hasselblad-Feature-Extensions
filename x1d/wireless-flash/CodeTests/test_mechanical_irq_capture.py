"""执行实际 ARM 候选、官方分发器及官方 FromISR 队列代码；MMIO 为显式模型。"""
from pathlib import Path
import hashlib
import io
import json
import struct
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
sys.path.insert(0,str(ROOT/'x1d/tools'))
from elftools.elf.elffile import ELFFile
import unicorn
from unicorn import arm_const as arm

OUT=HERE/'build/mechanical-irq-candidate'
FARM=None
ELF_PATH=OUT/'irq-simulation.elf'
BOTH=0x0c000000
STACK,BUFFER,STOP,QUEUE=0x3000000,0x3100000,0x3200000,0x6d5000


class Machine:
    def __init__(self,real_queue=True,patched=True):
        if not isinstance(FARM,bytes) or hashlib.sha256(FARM).hexdigest()!='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca':
            raise ValueError('需要固定官方 FARM')
        u=self.u=unicorn.Uc(unicorn.UC_ARCH_ARM,unicorn.UC_MODE_ARM)
        farm_length=(len(FARM)+4095)&~4095
        u.mem_map(0x100000,farm_length); u.mem_write(0x100000,FARM)
        elf=ELFFile(io.BytesIO(ELF_PATH.read_bytes()))
        self.symbols={s.name:s['st_value'] for section in elf.iter_sections() if section['sh_type']=='SHT_SYMTAB' for s in section.iter_symbols()}
        self.record=self.symbols['mechanical_sync_record']
        allocated=set()
        for section in elf.iter_sections():
            if not section['sh_flags']&2 or not section['sh_size']: continue
            start,end=section['sh_addr'],section['sh_addr']+section['sh_size']
            for page in range(start&~4095,(end+4095)&~4095,4096):
                if not 0x100000<=page<0x100000+farm_length and page not in allocated:
                    u.mem_map(page,4096); allocated.add(page)
            u.mem_write(start,section.data())
        for address,word,name in ((0x21409c,0xeb0091df,'mechanical_sync_clear_hook'),
                (0x21410c,0xeb0091c3,'mechanical_sync_start_hook'),
                (0x213e60,0xeb0092cd,'mechanical_sync_status_hook'),
                (0x213ef8,0xeb0092a7,'mechanical_sync_status_hook'),
                (0x2143e4,0xeb00916c,'mechanical_sync_finish_hook')):
            assert struct.unpack('<I',u.mem_read(address,4))[0]==word
            if patched:
                delta=(self.symbols[name]-address-8)//4
                assert -(1<<23)<=delta<(1<<23)
                u.mem_write(address,struct.pack('<I',0xeb000000|(delta&0xffffff)))
        for base,length in ((0x6b0000,0x30000),(STACK,0x4000),(BUFFER,0x1000),
                            (0xf8f00000,0x2000),(0x42000000,0x1000)):
            u.mem_map(base,length)
        self.enabled=self.pending=self.active=0
        self.writes=[]; self.attempts=[]; self.task_attempts=[]; self.real_queue=real_queue
        self.extra_writable=set() # 组合装载测试可显式提供自有 scratch 单字；默认为空。
        self.wake=0; self.entered_original_queue=0
        self.control_writes=[]; self.clear_status=1; self.started_status=4; self.status_value=4
        for address,value in ((0x6da728,0x2a4ff0),(0x6da72c,0x11111111),
                              (0x2a52cc,0x109304),(0x2a52d0,0x6da728),(0x2a52d4,0x109304),(0x2a52d8,0x6da728),
                              (0xf8f01458,0x88776655),(0xf8f01858,0x04030201),(0xf8f01c14,0x55555555),
                              (0xf8f00104,0xff),(0xf8f00108,2),(0xf8f00114,0xa0),
                              (0xf8f00200,123),(0xf8f00204,7),(0xf8f00208,1),(0x42000014,1),
                              (0x6c4df4,QUEUE),(QUEUE,BUFFER),(QUEUE+4,BUFFER+4*287),
                              (QUEUE+8,BUFFER),(QUEUE+0x3c,4),(QUEUE+0x40,287),(QUEUE+0x48,0xffffffff)):
            self.put(address,value)
        u.reg_write(arm.UC_ARM_REG_C1_C0_2,0xf<<20)
        u.reg_write(arm.UC_ARM_REG_FPEXC,0x40000000)

        def instruction(uc,address,size,data):
            if address in (0x238820,0x23899c):
                args=[uc.reg_read(getattr(arm,'UC_ARM_REG_R'+str(i))) for i in range(4)]
                assert uc.reg_read(arm.UC_ARM_REG_SP)%8==0
                if address==0x238820:
                    assert args[0]==0x42000010 and args[1] in (0,0x40,3,7,0x302)
                    self.control_writes.append(tuple(args))
                    self.put(0x42000014,self.clear_status if args[1] in (0,0x40) else self.started_status)
                    uc.reg_write(arm.UC_ARM_REG_R0,0xaabb)
                else:
                    assert args[0]==0x42000014
                    uc.reg_write(arm.UC_ARM_REG_R0,self.status_value)
                uc.reg_write(arm.UC_ARM_REG_R12,0x1122)
                uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
                return
            if address in (0x2209f4,0x10a1f8):
                raise AssertionError('原厂断言触发: '+hex(address))
            if address in (0x1867e4,0x186500):
                args=[uc.reg_read(getattr(arm,'UC_ARM_REG_R'+str(i))) for i in range(4)]
                assert args[0]==QUEUE and args[3]==0
                assert uc.reg_read(arm.UC_ARM_REG_SP)%8==0
                packet=bytes(uc.mem_read(args[1],287))
                assert packet[:4]==bytes.fromhex('09000105') and not any(packet[48:])
                if address==0x1867e4:
                    assert STACK<=args[2]<STACK+0x4000
                    self.attempts.append(packet)
                    if self.real_queue:
                        self.entered_original_queue+=1
                        return
                    self.put(args[2],self.wake)
                else:
                    assert args[2]==0
                    self.task_attempts.append(packet)
                uc.reg_write(arm.UC_ARM_REG_R0,1)
                uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))

        def write(uc,access,address,size,value,data):
            self.writes.append((address,size,value))
            if address in self.extra_writable and size==4: return
            if address in (0xf8f01108,0xf8f01188,0xf8f01288):
                assert size==4 and not value&~BOTH
                if address==0xf8f01108: self.enabled|=value
                if address==0xf8f01188: self.enabled&=~value
                if address==0xf8f01288: self.pending&=~value
                return
            if address in (0xf8f01458,0xf8f01858,0xf8f01c14,0xf8f00104): return
            if address in (0x2a52cc,0x2a52d0,0x2a52d4,0x2a52d8,0x6bacc4): return
            if self.record<=address and address+size<=self.record+108: return
            if STACK<=address and address+size<=STACK+0x4000: return
            if BUFFER<=address and address+size<=BUFFER+4*287: return
            if QUEUE<=address and address+size<=QUEUE+0x50: return
            raise AssertionError('超出候选/显式队列模型的写入: '+hex(address))

        def read(uc,access,address,size,value,data):
            if address in (0xf8f01108,0xf8f01208,0xf8f01308):
                self.put(address,{0xf8f01108:self.enabled,0xf8f01208:self.pending,0xf8f01308:self.active}[address])
            if address>=0x40000000:
                assert size==4 and address in (0x42000014,0xf8f01108,0xf8f01208,0xf8f01308,
                    0xf8f01458,0xf8f01858,0xf8f01c14,0xf8f00104,0xf8f00108,0xf8f00114,
                    0xf8f00200,0xf8f00204,0xf8f00208),hex(address)
        u.hook_add(unicorn.UC_HOOK_CODE,instruction)
        u.hook_add(unicorn.UC_HOOK_MEM_WRITE,write)
        u.hook_add(unicorn.UC_HOOK_MEM_READ,read)

    def put(self,address,value): self.u.mem_write(address,struct.pack('<I',value))
    def word(self,address): return struct.unpack('<I',self.u.mem_read(address,4))[0]
    def field(self,offset): return self.word(self.record+offset)
    def call(self,name,*args):
        u=self.u
        u.reg_write(arm.UC_ARM_REG_CPSR,0x60000153)
        u.reg_write(arm.UC_ARM_REG_SP,STACK+0x3000)
        u.reg_write(arm.UC_ARM_REG_LR,STOP)
        for i in range(4): u.reg_write(getattr(arm,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
        address=self.symbols[name] if isinstance(name,str) else name
        u.emu_start(address,STOP,count=30000)
        assert u.reg_read(arm.UC_ARM_REG_PC)==STOP,'未正常返回'
        return u.reg_read(arm.UC_ARM_REG_R0)
    def start(self,mode=0):
        self.put(self.record+4,1)
        self.call('mechanical_sync_cancel_old',self.record)
        assert self.call('mechanical_sync_begin',self.record,mode)==0x40
        self.call('mechanical_sync_cleared',self.record)
    def irq(self,number):
        self.active=1<<(number-64)
        self.call(0x18b034,number)
        self.active=0
    def registers(self):
        return ([self.u.reg_read(getattr(arm,'UC_ARM_REG_R'+str(i))) for i in range(13)],
                [self.u.reg_read(r) for r in (arm.UC_ARM_REG_SP,arm.UC_ARM_REG_LR,arm.UC_ARM_REG_CPSR)],
                [self.u.reg_read(getattr(arm,'UC_ARM_REG_D'+str(i))) for i in range(32)])
    def init_registers(self):
        self.u.reg_write(arm.UC_ARM_REG_CPSR,0xa80a01d3)
        for i in range(13): self.u.reg_write(getattr(arm,'UC_ARM_REG_R'+str(i)),0x11000000+i*0x10001)
        for i in range(32): self.u.reg_write(getattr(arm,'UC_ARM_REG_D'+str(i)),0x1122334400000000+i)
    def hook_start(self,caller=0x1c5244,arg0=0,mode=0,source=3,parent_mode=None,parent_return=None,parent_delta=0x160):
        u=self.u; self.init_registers()
        fp,sp=STACK+0xb04,STACK+0x9d0; parent=fp+parent_delta
        self.put(fp,caller); self.put(fp-4,parent)
        self.put(parent,parent_return if parent_return is not None else (0x1ce09c if mode==1 else 0x1ce080))
        u.mem_write(parent-0x14d,bytes([source])); u.mem_write(parent-0x14e,bytes([mode if parent_mode is None else parent_mode]))
        u.mem_write(fp-0x12d,bytes([arg0])); u.mem_write(fp-0x12e,bytes([mode])); self.put(fp-0xc,0)
        u.reg_write(arm.UC_ARM_REG_R11,fp); u.reg_write(arm.UC_ARM_REG_SP,sp); u.reg_write(arm.UC_ARM_REG_LR,0x21407c)
        u.emu_start(0x214084,0x214110,count=10000)
        assert u.reg_read(arm.UC_ARM_REG_PC)==0x214110 and u.reg_read(arm.UC_ARM_REG_SP)==sp
        return self.registers()
    def hook_status(self,value,site=0x213e60):
        self.status_value=value; self.init_registers()
        self.u.reg_write(arm.UC_ARM_REG_R11,STACK+0xb04); self.u.reg_write(arm.UC_ARM_REG_SP,STACK+0x9d0)
        self.u.emu_start(site-20,site+4,count=10000)
        assert self.u.reg_read(arm.UC_ARM_REG_PC)==site+4
        return self.registers()


class IrqCaptureTests(unittest.TestCase):
    def machine(self,**kwargs):
        m=Machine(**kwargs)
        self.assertEqual(m.call('mechanical_irq_setup',m.record),1)
        return m
    def test_setup_restore_and_neighbor_bits(self):
        m=self.machine()
        self.assertEqual(m.word(0xf8f01458),0xa0a06655)
        self.assertEqual(m.word(0xf8f01858),0x01010201)
        self.assertEqual(m.word(0xf8f01c14),0x55a55555)
        self.assertEqual(m.enabled,0)
        self.assertEqual(m.call('mechanical_irq_restore',m.record),1)
        self.assertEqual([m.word(a) for a in (0xf8f01458,0xf8f01858,0xf8f01c14)],
                         [0x88776655,0x04030201,0x55555555])
        self.assertEqual(m.word(0x2a52cc),0x109304)
    def test_setup_refuses_in_use_without_writes(self):
        for kind in ('enabled','pending','active','handler','priority_group','armed'):
            with self.subTest(kind=kind):
                m=Machine()
                if kind in ('enabled','pending','active'): setattr(m,kind,BOTH)
                elif kind=='handler': m.put(0x2a52cc,0x123400)
                elif kind=='priority_group': m.put(0xf8f00108,3)
                else: m.put(m.record+4,1)
                self.assertEqual(m.call('mechanical_irq_setup',m.record),0)
                self.assertTrue(all(STACK<=a<STACK+0x4000 for a,_,_ in m.writes))
    def test_real_dispatch_and_real_from_isr_copy(self):
        m=self.machine(); m.start()
        self.assertEqual(m.enabled,BOTH)
        m.put(0x42000014,4)
        m.irq(90); m.irq(90); m.irq(91); m.irq(91)
        self.assertEqual(m.entered_original_queue,2)
        self.assertEqual(m.field(60),2)
        self.assertEqual(m.word(QUEUE+0x38),2)
        self.assertEqual(m.enabled,0)
        for index,source in enumerate((2,3)):
            packet=bytes(m.u.mem_read(BUFFER+287*index,287))
            self.assertEqual(packet,m.attempts[index])
            fields=struct.unpack('<11I',packet[4:48])
            self.assertEqual(fields[:3],(0x31534d47,2,1))
            self.assertEqual(fields[3],(1<<(source+8))|4)
            self.assertEqual(fields[6:9],(123,7,1))
            (OUT/('irq-message-source-'+str(source)+'.bin')).write_bytes(packet[:260])
    def test_full_queue_drops_once_without_retry(self):
        m=self.machine(); m.start(); m.put(QUEUE+0x38,4)
        m.irq(90); m.irq(90)
        self.assertEqual(m.entered_original_queue,1)
        self.assertEqual(m.field(60),0); self.assertEqual(m.field(64),1)
        self.assertEqual(m.word(QUEUE+0x38),4)
    def test_bad_queue_size_stops_before_copy(self):
        m=self.machine(); m.start(); m.put(QUEUE+0x40,288)
        m.irq(91)
        self.assertEqual(m.entered_original_queue,0)
        self.assertEqual(m.field(64),1)
    def test_status_reads_do_not_generate_edges(self):
        m=self.machine(); m.start()
        for status in (4,0,4,1):
            m.put(0x42000014,status)
            m.call('mechanical_sync_observe',m.record)
            m.call('mechanical_sync_sample',m.record,status,0)
        self.assertFalse(m.attempts); self.assertFalse(m.task_attempts)
    def test_end_and_cancel_block_late_irq(self):
        m=self.machine(); m.start(); m.irq(91)
        m.call('mechanical_sync_sample',m.record,1,0)
        self.assertEqual(m.field(8),0); self.assertEqual(m.enabled,0)
        self.assertEqual(len(m.task_attempts),1)
        fields=struct.unpack('<11I',m.task_attempts[0][4:48])
        self.assertEqual(fields[3],0x8004)
        m.irq(90); self.assertEqual(len(m.attempts),1)
        m.put(0x42000014,1); m.start(); m.call('mechanical_sync_cancel_old',m.record)
        m.irq(91); self.assertEqual(len(m.attempts),1)
    def test_new_trial_and_invalid_clear(self):
        m=self.machine(); m.start(); m.irq(90)
        m.put(0x42000014,1); m.start(); m.irq(90)
        self.assertEqual(struct.unpack('<11I',m.attempts[-1][4:48])[2],2)
        m.put(0x42000014,4); m.start()
        self.assertEqual(m.field(8),0); self.assertEqual(m.enabled,0)
    def test_wake_request_uses_original_irq_return_flag(self):
        m=self.machine(real_queue=False); m.wake=1; m.start(); m.irq(90)
        self.assertEqual(m.word(0x6bacc4),1)
        self.assertEqual(m.field(60),1)
    def test_restore_requires_disarmed_inactive_owner(self):
        m=self.machine(); m.start()
        self.assertEqual(m.call('mechanical_irq_restore',m.record),0)
        m.call('mechanical_sync_cancel_old',m.record); m.put(m.record+4,0)
        m.active=BOTH
        self.assertEqual(m.call('mechanical_irq_restore',m.record),0)
        m.active=0
        self.assertEqual(m.call('mechanical_irq_restore',m.record),1)
    def test_actual_call_hooks_preserve_original_registers_and_control(self):
        for mode,control in ((0,3),(1,7)):
            m=self.machine(); b=Machine(patched=False)
            m.put(m.record+4,1)
            self.assertEqual(m.hook_start(mode=mode),b.hook_start(mode=mode))
            self.assertEqual([w[1] for w in m.control_writes],[0x40,control])
            self.assertEqual([w[1] for w in b.control_writes],[0,control])
            self.assertEqual(m.field(8),2); self.assertEqual(m.enabled,BOTH)
            self.assertFalse(m.attempts)
            m.irq(90); m.irq(91)
            for site,value in ((0x213e60,4),(0x213ef8,4),(0x2143e4,1)):
                self.assertEqual(m.hook_status(value,site),b.hook_status(value,site))
            self.assertEqual(m.enabled,0)
    def test_actual_call_guards_reject_unrelated_starts(self):
        for args in ({'caller':0x1c437c},{'arg0':1},{'mode':2},{'source':1},
                     {'parent_mode':1},{'parent_return':0},{'parent_delta':0x164}):
            with self.subTest(args=args):
                m=self.machine(); b=Machine(patched=False); m.put(m.record+4,1)
                self.assertEqual(m.hook_start(**args),b.hook_start(**args))
                self.assertEqual(m.control_writes,b.control_writes)
                self.assertEqual(m.field(12),0); self.assertEqual(m.enabled,0)
                self.assertFalse(m.attempts)


def run(farm):
    global FARM,ELF_PATH
    FARM=farm
    reports=[]
    for name in ('irq-simulation','irq-target'):
        ELF_PATH=OUT/(name+'.elf')
        stream=io.StringIO()
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IrqCaptureTests))
        print(stream.getvalue())
        reports.append({'variant':name,'tests':result.testsRun,'passed':result.wasSuccessful(),
                        'elfSha256':hashlib.sha256(ELF_PATH.read_bytes()).hexdigest()})
        if not result.wasSuccessful(): break
    report={'passed':len(reports)==2 and all(r['passed'] for r in reports),'variants':reports,
            'hardwareRequests':0,'installed':False,'realInstructions':['候选 ARM','原厂中断分发器','原厂 FromISR 队列复制及满队列分支'],
            'explicitModels':['GIC/传感器/计时器 MMIO','队列/栈 RAM','结束通知的任务发送替身','唤醒场景的 FromISR 返回替身'],
            'physicalTimingMeasured':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'irq-capture-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    from farm_diagnostic_binary import FarmApplication
    result=run(FarmApplication().data)
    if not result['passed']: raise SystemExit(1)
