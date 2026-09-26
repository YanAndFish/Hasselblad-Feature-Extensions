"""实际 ARM 库调用边界与原厂 transport 返回分支；全部设备及 OS 依赖为替身。"""
import importlib.util,io,struct,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];COMMON=HERE.parents[1]
LIB=HERE/'linux-build/libhbl-af-bus.so'
spec=importlib.util.spec_from_file_location('bus_transport_original_startup',COMMON/'CodeTests/test_bus_startup_r2.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
old.LIB=LIB
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile
Base=old.ArmConnect
ACTIVATE='_ZN11QMetaObject8activateEP7QObjectPKS_iPPv'
PREPACKED='MSGTRANP_send_prepacked'
def word(v):return struct.pack('<I',v&0xffffffff)
def request():
    data=bytearray(261);data[:6]=b'\x0f\x03\x05\x01\0\xff'
    struct.pack_into('<6I',data,6,0x414c4248,0x21345346,4,1,123,456)
    h=2166136261
    for b in data[6:257]:h=((h^b)*16777619)&0xffffffff
    data[257:]=word(h);return bytes(data)
class ArmTransport(Base):
    def stub(self,name):
        if name=='_ZN10QArrayData11shared_nullE':
            self.u.mem_write(0x3000800,word(-1)+word(0)+word(0)+word(16)+b'\0')
            return 0x3000800
        return super().stub(name)
    def hook(self,u,a,size,data):
        name=self.stubs.get(a)
        r=[u.reg_read(reg) for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        if name=='dlsym':
            symbol=self.string(r[1])
            choices={'_ZN15MsgTranspWriter16staticMetaObjectE':0x3000380,
                '_ZN16SerialPortWorker16staticMetaObjectE':0x30003c0,
                PREPACKED:self.stub('original-prepacked'),ACTIVATE:self.stub('original-activate')}
            if symbol in choices:
                u.reg_write(UC_ARM_REG_R0,choices[symbol]);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
        if name in ('original-prepacked','original-activate'):
            self.forwarded.append((name,r[:3] if name=='original-prepacked' else r,self.word(self.errno)))
            self.put(self.errno,91)
            u.reg_write(UC_ARM_REG_R0,getattr(self,'result',0)&0xffffffff)
            u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
        if name in ('pthread_mutex_lock','pthread_mutex_unlock'):
            u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
        if name=='_ZN10QArrayData10deallocateEPS_jj':
            raise AssertionError('borrowed packet must remain referenced')
        if name=='_ZN10QByteArrayaSERKS_':
            pointer=self.word(r[1]);self.put(r[0],pointer)
            if self.word(pointer)!=0xffffffff:self.put(pointer,self.word(pointer)+1)
            u.reg_write(UC_ARM_REG_R0,r[0]);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
        return super().hook(u,a,size,data)
    def invoke(self,name,args):
        self.forwarded=[];self.put(self.errno,33)
        sp=0x400f000
        for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):self.u.reg_write(reg,v)
        self.u.reg_write(UC_ARM_REG_SP,sp);self.u.reg_write(UC_ARM_REG_LR,0x200f000)
        self.u.emu_start(self.symbols[name],0x200f000,count=200000)
        assert self.u.reg_read(UC_ARM_REG_PC)==0x200f000 and self.u.reg_read(UC_ARM_REG_SP)==sp
        assert self.word(self.errno)==91
        return self.u.reg_read(UC_ARM_REG_R0)
old.ArmConnect=ArmTransport
class TransportTests(unittest.TestCase):
    def test_real_wrapper_forwards_once_and_preserves_all_return_classes(self):
        for enabled in (False,True):
            for result in (0,-1,-2,17):
                m=ArmTransport(enabled=enabled);m.result=result
                p=0x3020000;m.u.mem_write(p,request());args=[0x903000,p,261]
                self.assertEqual(m.invoke(PREPACKED,args),result&0xffffffff)
                self.assertEqual(m.forwarded,[('original-prepacked',args,33)])
                self.assertEqual(bytes(m.u.mem_read(p,261)),request())
    def test_real_wrapper_passes_foreign_and_short_packets_unchanged(self):
        for data in (b'x',bytes(261),request()[:-1]):
            m=ArmTransport();m.result=-1;p=0x3020000;m.u.mem_write(p,data);args=[0x903000,p,len(data)]
            self.assertEqual(m.invoke(PREPACKED,args),0xffffffff)
            self.assertEqual(m.forwarded,[('original-prepacked',args,33)])
    def test_actual_activate_forwards_and_does_not_use_caller_timer(self):
        m=ArmTransport();m.call();m.queues=[]
        raw=b'\x10\x03\x01\x05'+bytes(255)
        m.u.mem_write(0x3020000,word(100)+word(len(raw))+word(260)+word(16)+raw)
        m.put(0x3021000,0x3020000);m.put(0x3022000,0);m.put(0x3022004,0x3021000)
        args=[m.owner,m.message_meta,0,0x3022000]
        m.invoke(ACTIVATE,args)
        self.assertEqual(m.forwarded,[('original-activate',args,33)])
        self.assertEqual(len(m.queues),0) # owner discovered but mock has no instantiated Bus; fail closed, never create a caller timer
        self.assertEqual(bytes(m.u.mem_read(0x3020010,259)),raw)
    def test_activity_signals_forward_once_without_scheduling_reply(self):
        m=ArmTransport();m.call();m.queues=[]
        for meta,signal in ((0x3000380,0),(0x30003c0,0),(0x30003c0,2),(m.uart_meta,0)):
            args=[m.owner,meta,signal,0]
            m.invoke(ACTIVATE,args)
            self.assertEqual(m.forwarded,[('original-activate',args,33)])
        self.assertFalse(m.queues)
    def test_original_transport_has_separate_link_gate_after_writer_acceptance(self):
        path=old.ROOT/'.research-cache/x1d-1.25.0/usb-diagnostic-inputs/usr/lib/libAppsMessaging.so'
        import hashlib
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),'8a6a45428fcaa17e570e0aad217ee7220716501bcaf4cddef106af5137d6f7d1')
        elf=ELFFile(io.BytesIO(path.read_bytes()));u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x4adf0000,0x40000);u.mem_map(0x900000,0x10000)
        for seg in elf.iter_segments():
            if seg['p_type']=='PT_LOAD':u.mem_write(seg['p_vaddr'],seg.data())
        u.mem_write(0x901018,word(0x900004));posts=[]
        def hook(uc,a,size,data):
            if a==0x4adf46a4:
                posts.append(tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)))
            if a in (0x4adf46a4,0x900004):
                uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        for queue,state,length,want in ((0,2,261,-2),(0x905000,1,261,-1),(0x905000,2,321,-2),(0x905000,2,261,0)):
            posts.clear();u.mem_write(0x9020d8,word(queue));u.mem_write(0x90101c,bytes([state]))
            u.reg_write(UC_ARM_REG_R0,0x901000);u.reg_write(UC_ARM_REG_R1,0x904000);u.reg_write(UC_ARM_REG_R2,length)
            u.reg_write(UC_ARM_REG_SP,0x90ff00);u.reg_write(UC_ARM_REG_LR,0x900000)
            u.emu_start(0x4adf63e8,0x900000,count=10000)
            self.assertEqual(u.reg_read(UC_ARM_REG_R0),want&0xffffffff)
            self.assertEqual(posts,[(0x901000,0x904000,261)] if want==0 else [])
def suite():
    result=unittest.TestSuite()
    result.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(old.StartupTests))
    result.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TransportTests))
    return result
