"""执行成对缓存同步 thunk 和原厂缓存函数；所有 MMIO 仅为模拟器内存。"""
from pathlib import Path
import sys,struct,hashlib,json,re
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
source=P/'build/cache-pair/cache_pair_loader.cpp'
text=source.read_text(encoding='utf-8');body=text.split('thunkWords[]={',1)[1].split('};',1)[0]
words=[int(x,16) for x in re.findall(r'0x([a-f0-9]+)',body)]
blob=struct.pack('<%dI'%len(words),*words);assert len(blob)==36
firmware=(P/'build/fast-start-research/farm-1.25.0.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest()=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
def run(size,stop):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
 u.mem_map(0x100000,0x700000);u.mem_map(0x8000,0x2000);u.mem_map(0xf8f02000,0x1000)
 u.mem_write(0x100000,firmware);u.mem_write(0x2b2800,blob)
 desc=0x2b2828;start=0x19b960
 u.mem_write(desc,struct.pack('<5I',start,size,0x10a270,0x10a354,0))
 u.reg_write(UC_ARM_REG_CPSR,0x13);u.reg_write(UC_ARM_REG_R0,desc);u.reg_write(UC_ARM_REG_R4,0x76543210)
 u.reg_write(UC_ARM_REG_SP,0x7effe0);u.reg_write(UC_ARM_REG_LR,0x9000)
 calls=[]
 def trace(m,a,n,c):
  if a in (0x10a270,0x10a354):
   calls.append(a);assert m.reg_read(UC_ARM_REG_R0)==start and m.reg_read(UC_ARM_REG_R1)==size
   assert bytes(m.mem_read(desc+16,4))==bytes(4)
   if a==stop:m.emu_stop()
 u.hook_add(UC_HOOK_CODE,trace);u.emu_start(0x2b2800,0x9000,count=100000)
 if stop:assert bytes(u.mem_read(desc+16,4))==bytes(4)
 else:
  assert u.reg_read(UC_ARM_REG_PC)==0x9000 and u.reg_read(UC_ARM_REG_SP)==0x7effe0 and u.reg_read(UC_ARM_REG_R4)==0x76543210
  assert calls==[0x10a270,0x10a354] and bytes(u.mem_read(desc+16,4))==struct.pack('<I',1)
  assert bytes(u.mem_read(desc,16))==struct.pack('<4I',start,size,0x10a270,0x10a354)
 return dict(size=size,stop=stop,passed=True)
r=dict(passed=True,cases=[run(n,stop) for n in (32,2704,2976) for stop in (0,0x10a270,0x10a354)],hardwareRequests=0,sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),originalCacheFunctionsExecuted=True)
(P/'build/cache-pair/arm-validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
