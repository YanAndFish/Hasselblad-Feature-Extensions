"""真实 ARM 初始化器、原缓存函数及原 AF proof；不访问相机。"""
from pathlib import Path
import sys,re,struct,json,hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
out=P/'build/task-cache';blob=(out/'initializer.bin').read_bytes()
build=json.loads((out/'build.json').read_text(encoding='utf-8'))
def image_at(address):
 b=bytearray(blob);delta=address-build['base']
 for off in build['fixups']:struct.pack_into('<I',b,off,struct.unpack_from('<I',b,off)[0]+delta)
 for lo,hi in build['movPairs']:
  a,c=struct.unpack_from('<I',b,lo)[0],struct.unpack_from('<I',b,hi)[0]
  val=((a&4095)|((a>>4)&61440)|(((c&4095)|((c>>4)&61440))<<16))+delta
  for off,w,v in ((lo,a,val&65535),(hi,c,val>>16)):struct.pack_into('<I',b,off,(w&~0xf0fff)|((v&61440)<<4)|(v&4095))
 return bytes(b)
firmware=(P/'build/fast-start-research/farm-1.25.0.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest()=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
contract=(out/'contract.h').read_text(encoding="utf-8");constants={k:int(v,16) for k,v in re.findall(r'#define (\w+) (0x[0-9a-f]+)u',contract)}
hooks=[tuple(int(v,16) for v in row) for row in re.findall(r'\{(0x[0-9a-f]+)u,(0x[0-9a-f]+)u,(0x[0-9a-f]+)u\}',contract)]
af=(P/'build/boot-data/af_relocation_data.h').read_text(encoding="utf-8")
words=[int(x,16) for x in re.findall(r'0x([0-9a-f]+)u',af.split('hbl_af_words[] = {')[1].split('};')[0])]
relocs=[tuple(map(int,row)) for row in re.findall(r'\{(\d+),(\d+),(\d+)\}',af.split('hbl_af_relocations')[1])]
def relocated(heap):
 b=bytearray(struct.pack('<%dI'%len(words),*words))
 for off,kind,target in relocs:
  value=heap+target
  if kind==2:struct.pack_into('<I',b,off,value)
  else:
   hi,lo=struct.unpack_from('<HH',b,off);value=(value>>(16 if kind==48 else 0))&65535
   hi=(hi&~0x40f)|(value>>12)|((value&0x800)>>1);lo=(lo&~0x70ff)|((value&0x700)<<4)|(value&255)
   struct.pack_into('<HH',b,off,hi,lo)
 return b
def run(heap,fault=None,stop_write=0):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
 u.mem_map(0x100000,0x700000);u.mem_map(0x8000,0x2000);u.mem_map(0xf8f02000,0x1000)
 u.mem_write(0x100000,firmware);u.mem_write(heap+8192,image_at(heap+8192))
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 r=heap+24576
 put(heap-8,0);put(heap-4,32808|0x80000000)
 u.mem_write(r,struct.pack('<6I',0x31494641,heap,32808,123,0,0))
 u.mem_write(heap+4096,bytes(relocated(heap)))
 for a,v,_ in hooks:put(a,v)
 put(0x19b960,constants['GATE_BRANCH']);put(0x2b37b4,0)
 for a,v in [(0x6bb46c,0),(0x6bb598,0),(0x2adc78,0x1200),(0x2adc8c,0)]:put(a,v)
 put(0x23acac,3942768383);put(0x1e2224,3942859300)
 put(2830432,0);put(2830452,0)
 put(0x2a5074,heap+8192);put(0x2a5078,r)
 u.mem_write(0x2b2800,bytes([0x55])*64)
 if fault=='receiver':put(0x23acac,0)
 if fault=='mailbox':put(2830432,1)
 if fault=='callback':put(0x2a5074,0)
 if fault=='heap':put(heap-4,0)
 if fault=='gate':put(0x19b960,0)
 if fault=='busy':put(0x6bb46c,1)
 if fault=='hook':put(hooks[-1][0],0)
 if fault=='reentry':put(r+16,1)
 u.reg_write(UC_ARM_REG_CPSR,0x13);u.reg_write(UC_ARM_REG_R0,r)
 u.reg_write(UC_ARM_REG_SP,0x7effe0);u.reg_write(UC_ARM_REG_LR,0x9000)
 calls=[];writes=[]
 def trace(m,a,n,c):
  if a in (0x10a270,0x10a354):calls.append((a,m.reg_read(UC_ARM_REG_R0),m.reg_read(UC_ARM_REG_R1)))
 def write(m,access,a,n,v,c):
  if heap<=a<heap+constants['AF_BYTES'] or 0x2b2800<=a<0x2b2840 or a in [x[0] for x in hooks]+[0x19b960,0x2b37b4,0x23acac,0x1e2224,0x2a5074,0x2a5078]:
   writes.append((a,v))
   if stop_write and len(writes)==stop_write:m.emu_stop()
 u.hook_add(UC_HOOK_CODE,trace);u.hook_add(UC_HOOK_MEM_WRITE,write)
 u.emu_start(heap+8192,0x9000,count=500000)
 if fault:assert get(r+16)!=2 and not writes,(fault,writes)
 elif stop_write:assert get(r+16)!=2
 else:
  assert u.reg_read(UC_ARM_REG_PC)==0x9000,(hex(u.reg_read(UC_ARM_REG_PC)),get(r+20))
  assert (get(r+16),get(r+20))==(2,0),(get(r+16),get(r+20))
  assert get(0x19b960)==constants['GATE_ORIGINAL'] and get(0x2b37b4)==2
  # 每个发布点的实际原厂清理/失效必须连续且覆盖准确范围。
  ranges=[(heap,constants['AF_BYTES'])]+[(a&~31,32) for a,_,_ in hooks]+[(0x19b960&~31,32),(0x23acac&~31,32),(0x1e2224&~31,32),(0x2b2800,64)]
  expected=[(fn,a,n) for a,n in ranges for fn in (0x10a270,0x10a354)]
  assert calls==expected,(calls,expected)
  assert get(0x23acac)==0xeb0008bc and get(0x1e2224)==0xebfffd4f
  assert get(0x2a5074)==0x109304 and get(0x2a5078)==0x6da728
  assert bytes(u.mem_read(0x2b2800,64))==bytes(64)
  assert u.reg_read(UC_ARM_REG_SP)==0x7effe0
 return dict(heap=heap,fault=fault,stopWrite=stop_write,writes=len(writes),passed=True)
cases=[]
for heap in (0x398ea0,0x450000):
 good=run(heap);cases.append(good)
 for fault in ('heap','gate','busy','hook','reentry','receiver','mailbox','callback'):cases.append(run(heap,fault))
 for stop in range(1,good["writes"]+1):cases.append(run(heap,stop_write=stop))
r=dict(passed=True,cases=cases,hardwareRequests=0,initializerSha256=hashlib.sha256(blob).hexdigest(),testSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),originalCacheFunctionsExecuted=True,originalAFProofExecuted=True)
(out/'arm-validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,cases=len(cases),hardwareRequests=0)))

