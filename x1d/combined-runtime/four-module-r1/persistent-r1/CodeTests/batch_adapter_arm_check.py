"""真实ARM适配器重定位、解码转交和诊断执行模拟。原厂函数使用ABI替身。"""
from pathlib import Path
import sys,struct,json,zlib
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
out=P/'build/batch-model';r=json.loads((out/'adapter-build.json').read_text(encoding='utf-8'));original=(out/'adapter.bin').read_bytes()
def pack(*v):return struct.pack('<'+'I'*len(v),*v)
def run(base,kind):
 heap=base-16384;blob=bytearray(original);delta=base-r['base']
 for off in r['fixups']:struct.pack_into('<I',blob,off,struct.unpack_from('<I',blob,off)[0]+delta)
 for lo,hi in r['movPairs']:
  a,b=struct.unpack_from('<I',blob,lo)[0],struct.unpack_from('<I',blob,hi)[0]
  imm=lambda w:(w&4095)|((w>>4)&61440)
  v=(imm(a)|(imm(b)<<16))+delta
  put=lambda w,x:(w&~0x000f0fff)|((x&61440)<<4)|(x&4095)
  struct.pack_into('<I',blob,lo,put(a,v&65535));struct.pack_into('<I',blob,hi,put(b,v>>16))
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9);u.mem_map(0x100000,0x700000);u.mem_map(0x8000,0x2000);u.mem_write(0x100000,(P/'build/fast-start-research/farm-1.25.0.bin').read_bytes());u.mem_write(base,bytes(blob))
 branch=0xeb000000|(((base+r['symbols']['hbl_batch_decode']-0x23acac-8)//4)&0xffffff)
 u.mem_write(0x23acac,pack(branch));u.mem_write(0x730018,pack(0x9004))
 ctx=base+r['symbols']['hbl_batch_adapter'];token=ctx+16
 u.mem_write(ctx,pack(1,heap,1,0,token,0,42,0,0));events=[];control=1 if kind=='control' else 0
 op=1 if kind=='compare' else 2;target=base if kind=='denied' else heap
 payload=pack(0x31424248,42,0,op,1,0 if op==1 else target,0)+(pack(target,7,0xffffffff) if op==1 else pack(7))
 frame=b'\xf4\x00\x05\x01'+payload;frame+=pack(zlib.crc32(frame))
 if kind=='crc':frame=frame[:-1]+bytes([frame[-1]^1])
 if kind=='legacy':frame=b'\xf4\x00\x05\x01'+pack(heap)
 if kind=='compare':u.mem_write(heap,pack(7))
 def hook(m,a,n,c):
  if a==0x23cfa4:
   assert m.reg_read(UC_ARM_REG_R0)==0x700000 and m.reg_read(UC_ARM_REG_R2)==0x710000 and m.reg_read(UC_ARM_REG_R3)==0x720000
   sp=m.reg_read(UC_ARM_REG_SP);assert bytes(m.mem_read(sp,8))==pack(0x720004,0x720008)
   count=m.reg_read(UC_ARM_REG_R1);m.mem_write(0x710000,bytes(m.mem_read(0x700000,count)));m.mem_write(0x720008,bytes([control]));m.reg_write(UC_ARM_REG_R0,count)
  elif a==0x1e80d0:
   reply=bytes(m.mem_read(m.reg_read(UC_ARM_REG_R0),287));assert reply[:4]==b'\xf5\x00\x01\x05' and not any(reply[9:]);events.append(reply[:9].hex());m.reg_write(UC_ARM_REG_R0,1)
  elif a in (0x9004,0x23a5c4):m.reg_write(UC_ARM_REG_R0,0)
  elif a==0x1e1768:events.append('legacy');assert m.reg_read(UC_ARM_REG_R0)==0x710000
  else:return
  m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 def call(symbol,args):
  for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,val)
  u.reg_write(UC_ARM_REG_SP,0x7effe0);u.mem_write(0x7effe0,pack(0x720000,0x720004,0x720008) if symbol=='original_decode' else pack(0x720004,0x720008));u.reg_write(UC_ARM_REG_LR,0x9000)
  
  try:u.emu_start(0x23ac64 if symbol=='original_decode' else base+r['symbols'][symbol],0x9000,count=100000)
  except Exception:
   print('failure pc',hex(u.reg_read(UC_ARM_REG_PC)),kind);raise
  assert u.reg_read(UC_ARM_REG_PC)==0x9000
  return u.reg_read(UC_ARM_REG_R0)
 u.mem_write(0x700000,frame);result=call('original_decode',[0x730000,0x700000,len(frame),0x710000])
 if kind=='crc':assert result==0xffffffff and not events;return dict(case=kind,base=base,passed=True)
 if kind in ('legacy','control'):
  assert result==len(frame) and bytes(u.mem_read(0x710000,len(frame)))==frame
  if kind=='legacy':call('hbl_batch_read_dispatch',[0x710000]);assert events==['legacy']
  return dict(case=kind,base=base,passed=True)
 assert result==8 and not events
 assert bytes(u.mem_read(heap,4))==(pack(7) if kind=='compare' else pack(0))
 call('hbl_batch_read_dispatch',[0x710000]);assert len(events)==1
 response=bytes.fromhex(events[0]);assert response[4:8]==pack(0) and response[8]==(5 if kind=='denied' else 0)
 if kind=='upload':assert bytes(u.mem_read(heap,4))==pack(7)
 call('hbl_batch_read_dispatch',[0x710000]);assert events[-1]=='legacy' and len(events)==2
 return dict(case=kind,base=base,passed=True)
cases=[run(base,kind) for base in (0x39a000,0x59ffc0) for kind in ('upload','compare','legacy','control','crc','denied')]
report=dict(passed=True,originalFarmLengthFilterExecuted=True,cases=cases,hardwareRequests=0,installed=False,adapterSha256=r['sha256'])
(out/'adapter-arm-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
