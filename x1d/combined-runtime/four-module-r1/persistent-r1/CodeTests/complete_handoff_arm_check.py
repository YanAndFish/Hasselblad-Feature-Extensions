"""微型接收器真实 ARM 与原厂外层解码链；不访问相机。"""
from pathlib import Path
import sys,io,struct,hashlib,json,zlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile
out=P/'build/complete-boot';blob=(out/'seed.bin').read_bytes()
elf=ELFFile(io.BytesIO((out/'seed.elf').read_bytes()))
symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
firmware=(P/'build/fast-start-research/farm-1.25.0.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest()=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
adapterElf=ELFFile(io.BytesIO((P/'build/block-write/staged_adapter.elf').read_bytes()))
adapterSymbols={s.name:s['st_value'] for s in adapterElf.get_section_by_name('.symtab').iter_symbols()}
target=bytearray((P/'build/block-write/staged_adapter.bin').read_bytes());assert len(target)==2776
context=adapterSymbols['hbl_batch_adapter'];struct.pack_into('<9I',target,context-0x2b2880,1,0,0,0,context+16,0,42,0,0)
target=bytes(target)
def pack(*x):return struct.pack('<'+'I'*len(x),*x)
def framed(payload,control=0):
 data=bytes([1,control])+payload;crc=65535
 for byte in data:
  crc^=byte
  for _ in range(8):crc=(crc>>1)^(0x8408 if crc&1 else 0)
 data+=struct.pack('<H',crc^65535)
 return b'\x7e'+b''.join(bytes([0x7d,x^0x20]) if x in (0x7d,0x7e) else bytes([x]) for x in data)+b'\x7e'
def run(kind):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
 u.mem_map(0x100000,0x700000);u.mem_map(0x8000,0x2000)
 u.mem_write(0x100000,firmware);u.mem_write(0x2b3400,blob)
 ctx=symbols['hbl_seed'];u.mem_write(ctx,pack(42,0,0,0))
 delta=(symbols['hbl_seed_decode']&~1)-0x23acac-8
 branch=0xfa000000|((delta>>2)&0xffffff)|((delta&2)<<23)
 u.mem_write(0x23acac,pack(branch));u.mem_write(0x730018,pack(0x9004))
 u.mem_write(0x2b2880,bytes(2776));u.mem_write(0x2b2474,b'\0')
 writes=[];replies=[]
 u.mem_write(0x2ae064,b"\0");u.mem_write(0x6c4df4,pack(0x740000))
 def trace(m,a,n,c):
  if a==0x186500:
   replies.append(bytes(m.mem_read(m.reg_read(UC_ARM_REG_R1),9)))
   m.reg_write(UC_ARM_REG_R0,1);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR));return
  if a in (0x9004,0x23a5c4,0x16017c,0x236b28):m.reg_write(UC_ARM_REG_R0,0);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
 def write(m,access,a,n,v,c):
  if 0x2b2880<=a<0x2b3400:
   assert a+n<=0x2b2880+2776;writes.append((a,v))
 u.hook_add(UC_HOOK_CODE,trace);u.hook_add(UC_HOOK_MEM_WRITE,write)
 def call(payload,control=0,badcrc=False):
  wire=framed(payload,control)
  if badcrc:wire=wire[:-3]+bytes([wire[-3]^1])+wire[-2:]
  u.mem_write(0x700000,wire)
  for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(0x730000,0x700000,len(wire),0x710000)):u.reg_write(reg,val)
  u.reg_write(UC_ARM_REG_SP,0x7effe0);u.mem_write(0x7effe0,pack(1024,0x720004,0x720008));u.reg_write(UC_ARM_REG_LR,0x9000)
  u.emu_start(0x23ac64,0x9000,count=100000)
  assert u.reg_read(UC_ARM_REG_PC)==0x9000
  return u.reg_read(UC_ARM_REG_R0)
 if kind=='success':
  packets=0
  for off in range(0,len(target),240):
   piece=target[off:off+240];assert call(pack(0x010500f4,0x31444553,42,off)+piece)==8
   assert bytes(u.mem_read(0x710000,8))==pack(0x010500f4,ctx+8)
   assert bytes(u.mem_read(ctx+8,8))==pack(off+len(piece),0);packets+=1
  assert bytes(u.mem_read(0x2b2880,2776))==target
  assert packets==12 and len(writes)==694
  # 同一模拟器、同一 RAM：由 seed 装入的接收器接管，再批量上传分配程序。
  v=0xeb000000|(((adapterSymbols['hbl_batch_decode']-0x23acac-8)//4)&0xffffff)
  u.mem_write(0x23acac,pack(v));u.ctl_remove_cache(0x23ac64,0x23ae20);u.mem_write(context+8,pack(3))
  data=pack(*range(60));payload=pack(0x010500f4,0x31424248,42,0,2,60,0x2b3400,0)+data
  payload+=pack(zlib.crc32(payload))
  assert call(payload)==8
  u.reg_write(UC_ARM_REG_R0,0x710000);u.reg_write(UC_ARM_REG_SP,0x7effe0);u.reg_write(UC_ARM_REG_LR,0x9000)
  u.emu_start(adapterSymbols['hbl_batch_read_dispatch'],0x9000,count=100000)
  assert u.reg_read(UC_ARM_REG_PC)==0x9000
  assert replies==[bytes.fromhex('f5000105')+pack(0)+b'\0']
  assert bytes(u.mem_read(0x2b3400,len(data)))==data
  # 上传分配程序已覆盖 seed；通信入口必须仍由新接收器处理。
  u.mem_write(context+4,pack(0x398ea0));u.mem_write(context+8,pack(1))
  payload=pack(0x010500f4,0x31424248,42,1,2,60,0x398ea0,0)+data;payload+=pack(zlib.crc32(payload))
  assert call(payload)==8
  u.reg_write(UC_ARM_REG_R0,0x710000);u.reg_write(UC_ARM_REG_SP,0x7effe0);u.reg_write(UC_ARM_REG_LR,0x9000)
  u.emu_start(adapterSymbols['hbl_batch_read_dispatch'],0x9000,count=100000)
  assert replies[-1]==bytes.fromhex('f5000105')+pack(1)+b'\0' and bytes(u.mem_read(0x398ea0,len(data)))==data
 else:
  payload=pack(0x010500f4,0x31444553,43 if kind=='nonce' else 42,4 if kind=='order' else 0)+pack(0x7d7e7d7e)
  if kind=='oversize':payload=payload[:16]+bytes(244)
  if kind=='unaligned':payload=payload[:-1]
  if kind=='empty':payload=payload[:16]
  if kind=='boundary':u.mem_write(ctx+4,pack(2776));payload=pack(0x010500f4,0x31444553,42,2776)+pack(1)
  if kind=='legacy':payload=pack(0x010500f4,0x2b2880)
  if kind=='repeat':assert call(payload)==8;writes.clear()
  result=call(payload,1 if kind=='control' else 0,kind=='crc')
  assert not writes,kind
  if kind not in ('legacy','control','crc'):
   assert result==8 and bytes(u.mem_read(ctx+8,8))==pack(0xffffffff,1)
   assert call(pack(0x010500f4,0x31444553,42,0)+pack(2))==8 and not writes
 return dict(case=kind,passed=True)
cases=[run(k) for k in ('success','nonce','order','oversize','unaligned','empty','boundary','repeat','legacy','control','crc')]
r=dict(passed=True,cases=cases,seedBytes=len(blob),adapterBytes=len(target),adapterUploadPackets=12,hardwareRequests=0,installed=False,originalOuterDecoderExecuted=True,originalCRC16Executed=True,seedSha256=hashlib.sha256(blob).hexdigest(),testSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),completeBootValidated=False,seedToAdapterToBootstrapHandoff=True)
(out/'handoff-arm-validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
