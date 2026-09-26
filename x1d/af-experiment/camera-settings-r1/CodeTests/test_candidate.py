"""执行新 ARM body 和原厂封包/方向 helper；全部外设为替身，无 USB。"""
import hashlib,json,struct,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
assert Path.cwd().resolve()==ROOT
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
FARM=FarmApplication();BUILD=HERE/'build/00800000'
M=json.loads((BUILD/'capture-manifest.json').read_text(encoding='utf-8'));PAYLOAD=(BUILD/'candidate.bin').read_bytes()
assert FARM.sha256==M['baseline_sha256'] and hashlib.sha256(PAYLOAD).hexdigest()==M['payload_sha256']
for name,digest in M['source_sha256'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
def pack(*values):return struct.pack('<'+'I'*len(values),*[v&0xffffffff for v in values])
def words(data):return struct.unpack('<'+'I'*(len(data)//4),data)
def checksum(data):
    h=2166136261
    for b in data:h=((h^b)*16777619)&0xffffffff
    return h
def config(revision=2,probe=9000,fast=20000,fine=5000,flags=1,time=0,fast_time=0):
    data=pack(0x33435441,3,75,revision,probe,fast,fine,flags,fast_time,time)
    return data+pack(checksum(data))
def request(op=1,expected=0,c=None):
    data=bytearray(255);data[:28]=pack(0x414c4248,0x21335346,3,op,123,456,expected)
    if c is not None:data[28:72]=c
    data[251:]=pack(checksum(data[:251]));return data
class Machine:
    def __init__(self):
        self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x100000,0x600000);self.u.mem_write(0x100000,FARM.data)
        self.u.mem_map(0x800000,0x10000);self.u.mem_write(M['base'],PAYLOAD);self.u.mem_map(0x900000,0x10000)
        self.sends=[];self.events=[];self.original_calls=0
        for a,old,new in M['emulatorOnlyHooks']:assert FARM.word(a)==old;self.u.mem_write(a,pack(new))
        self.u.mem_write(0x1e80d0,bytes.fromhex('1eff2fe1'));self.u.mem_write(0x236a14,bytes.fromhex('0000a0e31eff2fe1'));self.u.hook_add(UC_HOOK_CODE,self.hook)
        self.u.mem_write(0x2adc79,b'\x12');self.run('na_begin',1)
    def hook(self,u,a,size,data):
        if a==0x1a4890:self.events.append(u.reg_read(UC_ARM_REG_R0))
        if a==0x1e1e1c:self.original_calls+=1
        if a==0x1e80d0:
            p=u.reg_read(UC_ARM_REG_R0);header=bytes(u.mem_read(p,4));n=6 if header[:2]==b'\xcd\0' else 259
            self.sends.append(bytes(u.mem_read(p,n)));u.reg_write(UC_ARM_REG_R0,1)
    def run(self,name,*args):
        u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x1f);u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
        u.reg_write(UC_ARM_REG_SP,0x90fdf0);u.reg_write(UC_ARM_REG_LR,0x900000)
        for i in range(4,12):u.reg_write(globals()['UC_ARM_REG_R'+str(i)],0x12345000+i)
        for i in range(8,16):u.reg_write(globals()['UC_ARM_REG_D'+str(i)],0x0123456700000000+i)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v&0xffffffff)
        u.emu_start(M['symbols'].get(name,name),0x900000,count=300000)
        assert u.reg_read(UC_ARM_REG_PC)==0x900000 and u.reg_read(UC_ARM_REG_SP)==0x90fdf0
        assert all(u.reg_read(globals()['UC_ARM_REG_R'+str(i)])==0x12345000+i for i in range(4,12))
        assert all(u.reg_read(globals()['UC_ARM_REG_D'+str(i)])==0x0123456700000000+i for i in range(8,16))
        return u.reg_read(UC_ARM_REG_R0)
    def process(self,p,lens=18):
        self.u.mem_write(0x901000,bytes(p));self.run('as_process',0x901000,0x902000,3,lens)
        return bytes(self.u.mem_read(0x902000,255))
    def bank(self):return bytes(self.u.mem_read(M['symbols']['na_config_bank'],100))
    def native(self,cvs):
        n=len(cvs);self.u.mem_write(0x6bb46c,b'\x03');self.u.mem_write(0x6bc954,struct.pack('<H',n))
        self.u.mem_write(0x6bb5bc,pack(min(cvs)));self.u.mem_write(0x6bb5cc,pack(*cvs))
        self.u.mem_write(0x6bbd9c,struct.pack('<'+'h'*n,*[i*20 for i in range(n)]))
        value=self.run('na_direction',0x903000);return struct.unpack('<f',pack(value))[0]
class CandidateTests(unittest.TestCase):
    def test_factory_speeds_allow_independent_absolute_advances_and_restore(self):
        m=Machine()
        r=m.process(request(2,1,config(probe=0,fast=0,fine=0,fast_time=0,time=15)))
        self.assertEqual(words(r[24:28]),(0,))
        self.assertEqual(words(r[44:88])[4:10],(0,0,0,1,0,15))
        self.assertEqual(words(r[88:132])[8:10],(65534,65534))
        m.run('na_begin',2);m.run('na_stage_speed',1,6123)
        self.assertEqual(m.sends[-1][-2:],struct.pack('<h',6123))
        r=m.process(request(2,2,config(revision=3,probe=0,fast=0,fine=0,fast_time=65534,time=65534)))
        self.assertEqual(words(r[24:28]),(0,));self.assertEqual(words(r[44:88])[8:10],(65534,65534))

    def test_defaults_and_signed_original_packet(self):
        m=Machine();b=words(m.bank());self.assertEqual(b[7:13],(0,0,0,2,65534,65534))
        for stage,value in enumerate((3000,3000,3000)):
            for sign in (-1,1):
                m.run('na_stage_speed',stage,sign*3000);self.assertEqual(m.sends[-1],b'\xcd\0\x01\x03'+struct.pack('<h',-value if stage==0 else sign*value))
            m.run('na_stage_speed',stage,0);self.assertEqual(m.sends[-1][-2:],b'\0\0')
        m.u.mem_write(0x2adc79,b'\x13');m.run('na_stage_speed',1,3000);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',3000))
    def test_query_apply_ack_and_next_cycle(self):
        m=Machine();r=m.process(request());self.assertEqual(words(r[24:44]),(0,1,3,18,0))
        r=m.process(request(2,1,config(fast=15000)));self.assertEqual(words(r[24:28]),(0,));self.assertEqual(words(r[44:88])[3:6],(2,9000,15000))
        self.assertEqual(words(r[88:132])[3:6],(1,0,0))
        m.run('na_stage_speed',1,3000);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',3000))
        m.run('na_begin',2);m.run('na_stage_speed',1,-3000);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-15000))
        self.assertEqual(checksum(r[:251]),words(r[251:])[0])
    def test_conflict_malformed_and_lens_do_not_publish(self):
        for kind in ('stale','checksum','padding','speed','time','lens','query_payload'):
            m=Machine();before=m.bank();p=request(2,1,config());lens=18
            if kind=='stale':p=request(2,0,config())
            if kind=='checksum':p[60]^=1
            if kind=='padding':p[90]=1;p[251:]=pack(checksum(p[:251]))
            if kind=='speed':p=request(2,1,config(fast=32767))
            if kind=='time':p=request(2,1,config(time=201))
            if kind=='lens':lens=19
            if kind=='query_payload':p=request(1,1,config())
            r=m.process(p,lens);self.assertNotEqual(words(r[24:28])[0],0,kind);self.assertEqual(m.bank(),before,kind)
    def test_busy_snapshots_do_not_ack_success(self):
        m=Machine();m.u.mem_write(M['symbols']['na_config_bank'],pack(3));r=m.process(request())
        self.assertEqual(words(r[24:28])[0],6);self.assertEqual(r[44:132],bytes(88))
    def test_real_handler_and_nonowned_forwarding(self):
        m=Machine();p=b'\x0f\x03\x05\x01\0\xff'+bytes(request());m.u.mem_write(0x901000,p)
        m.run('as_receive_bridge',0x901000);self.assertEqual(m.original_calls,0);self.assertEqual(m.sends[-1][:4],b'\x10\x03\x01\x05')
        self.assertEqual(m.sends[-1][4:12],b'HBLAFR3!')
        foreign=bytearray(p);foreign[6]=0;m.u.mem_write(0x901000,bytes(foreign));m.run('as_receive_bridge',0x901000)
        self.assertEqual(m.original_calls,1);self.assertEqual(m.sends[-1][4:],bytes(foreign[6:]))
    def test_failed_first_three_roll_to_four_five_and_later(self):
        m=Machine();m.process(request(2,1,config()));m.run('na_begin',2)
        cvs=[1000,1100,1050,1200,1500,1510,1480,1700,2000]
        outcomes=[m.native(cvs[:n]) for n in range(3,len(cvs)+1)]
        self.assertEqual(outcomes[0:2],[0,0]);self.assertGreater(outcomes[2],0)
        self.assertEqual(outcomes[4],0);self.assertGreater(outcomes[-1],0)
    def test_factory_toggle_matches_original_helper(self):
        m=Machine()
        for cvs in ([1000,1100,1050],[1000,1300,1700],[1500,1200,800]):
            patched=m.native(cvs);raw=m.run(0x19e47c,0x903000)
            self.assertEqual(patched,struct.unpack('<f',pack(raw))[0])
    def test_far_preference_only_initial_probe_and_factory_bounded_reversal(self):
        m=Machine();m.u.mem_write(0x1a4890,bytes.fromhex('1eff2fe1'))
        m.process(request(2,1,config(flags=2)));m.run('na_begin',2)
        m.run('na_stage_speed',0,5000);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',-9000))
        m.run('na_stage_speed',1,5000);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',20000))
        m.u.mem_write(0x6bb46c,b'\x03');m.u.mem_write(0x6bb59f,b'\0');m.u.mem_write(0x6bb5a0,struct.pack('<h',-9000))
        before=len(m.sends);m.run(0x1a06e4)
        self.assertEqual(len(m.sends),before+1);self.assertEqual(m.sends[-1][-2:],struct.pack('<h',9000))
        self.assertEqual(bytes(m.u.mem_read(0x6bb59e,1)),b'\x01')
        # 新增的第二段失败仅在向near命令下触发；相反命令保留原厂state3路径。
        other=Machine();other.u.mem_write(0x1a4890,bytes.fromhex('1eff2fe1'))
        other.u.mem_write(0x6bb46c,b'\x03');other.u.mem_write(0x6bb59e,b'\x01')
        other.u.mem_write(0x6bb5a0,struct.pack('<h',-9000));other.run(0x1a0498)
        self.assertEqual(other.events,[]);self.assertEqual(other.sends[-1][-2:],struct.pack('<h',9000))
        m.run(0x1a0498);self.assertEqual(len(m.sends),before+1);self.assertEqual(m.events[-1],0x2000)
        m.u.mem_write(0x6bb46c,b'\x05');m.u.mem_write(0x6bb5a0,struct.pack('<h',9000))
        m.run(0x1a0498);self.assertEqual(m.events[-1],0x40000)
if __name__=='__main__':unittest.main(verbosity=2)
