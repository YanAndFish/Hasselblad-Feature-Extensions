"""真实 ARM 帧解码、CRC16、长度过滤与只读适配器验证；队列和诊断回调仍用 ABI 替身。"""
from pathlib import Path
import sys,struct,json,zlib
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
out=P/'build/controller-first'
import io,hashlib
from elftools.elf.elffile import ELFFile
staged='--staged' in sys.argv
e=ELFFile(io.BytesIO((out/('staged_adapter.elf' if staged else 'read_only_adapter.elf')).read_bytes()))
sections=[x for x in e.iter_sections() if x['sh_flags']&2 and x['sh_size']]
base=min(x['sh_addr'] for x in sections);end=max(x['sh_addr']+x['sh_size'] for x in sections)
original=bytearray(end-base)
for x in sections:
 if x['sh_type']!='SHT_NOBITS':original[x['sh_addr']-base:x['sh_addr']-base+x['sh_size']]=x.data()
r={'base':base,'fixups':[],'movPairs':[],'sha256':hashlib.sha256(original).hexdigest(),'symbols':{x.name:x['st_value']-base for x in e.get_section_by_name('.symtab').iter_symbols() if x.name in ('hbl_batch_decode','hbl_batch_read_dispatch','hbl_batch_adapter')}}

def pack(*v):return struct.pack('<'+'I'*len(v),*v)
def framed(payload,control):
 data=bytes([1,control])+payload
 crc=0xffff
 for byte in data:
  crc^=byte
  for _ in range(8):crc=(crc>>1)^(0x8408 if crc&1 else 0)
 data+=struct.pack('<H',crc^0xffff)
 return b'\x7e'+b''.join(bytes([0x7d,x^0x20]) if x in (0x7d,0x7e) else bytes([x]) for x in data)+b'\x7e'

def run(base,kind):
 heap=0x100770;blob=bytearray(original);delta=base-r['base']
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
 u.mem_write(ctx,pack(1,0,0,0,token,0,42,0,0));u.mem_write(0x2ae064,b'\x00');u.mem_write(0x6c4df4,pack(0x740000));u.mem_write(0x2b2474,b'\x00');events=[];control=1 if kind=='control' else 0
 op=2 if kind=='upload' else 1;target=0x800000 if kind=='denied' else heap
 value=0x7d7e7d7e if kind=='escaped' else 7
 item_count=20 if kind=='maximum' else 1
 payload=pack(0x31424248,43 if kind=='session' else 42,1 if kind=='sequence' else 0,op,item_count,0 if op==1 else target,0)+(pack(target,value,0 if kind=='mask' else 0xffffffff)*item_count if op==1 else pack(value))
 frame=b'\xf4\x00\x05\x01'+payload;frame+=pack(zlib.crc32(frame))
 if kind=='crc':frame=frame[:-1]+bytes([frame[-1]^1])
 if kind=='legacy':frame=b'\xf4\x00\x05\x01'+pack(heap)
 initial=0 if kind in ('upload','mismatch') else value
 u.mem_write(heap,pack(initial))
 def hook(m,a,n,c):
  if a==0x186500:
   assert m.reg_read(UC_ARM_REG_R0)==0x740000 and m.reg_read(UC_ARM_REG_R2)==500 and m.reg_read(UC_ARM_REG_R3)==0
   reply=bytes(m.mem_read(m.reg_read(UC_ARM_REG_R1),287));assert reply[:4]==b'\xf5\x00\x01\x05' and not any(reply[9:]);events.append(reply[:9].hex());m.reg_write(UC_ARM_REG_R0,0 if kind=='send-failure' else 1)
  elif a in (0x9004,0x23a5c4,0x16017c,0x236b28):m.reg_write(UC_ARM_REG_R0,0)
  elif a==0x1e1768:events.append('legacy');assert m.reg_read(UC_ARM_REG_R0)==0x710000
  else:return
  m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 def call(symbol,args):
  for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,val)
  u.reg_write(UC_ARM_REG_SP,0x7effe0);u.mem_write(0x7effe0,pack(1024,0x720004,0x720008) if symbol=='original_decode' else pack(0x720004,0x720008));u.reg_write(UC_ARM_REG_LR,0x9000)
  
  try:u.emu_start(0x23ac64 if symbol=='original_decode' else base+r['symbols'][symbol],0x9000,count=100000)
  except Exception:
   print('failure pc',hex(u.reg_read(UC_ARM_REG_PC)),kind);raise
  assert u.reg_read(UC_ARM_REG_PC)==0x9000
  return u.reg_read(UC_ARM_REG_R0)
 wire=framed(frame,control)
 if kind=='wire-crc':wire=wire[:-3]+bytes([wire[-3]^1])+wire[-2:]
 if kind=='delimiter':wire=b'\x00'+wire[1:]
 u.mem_write(0x700000,wire);result=call('original_decode',[0x730000,0x700000,len(wire),0x710000])
 if kind in ('crc','wire-crc','delimiter'):assert result==0xffffffff and not events;return dict(case=kind,base=base,passed=True)
 if kind in ('legacy','control'):
  assert result==len(frame) and bytes(u.mem_read(0x710000,len(frame)))==frame
  if kind=='legacy':call('hbl_batch_read_dispatch',[0x710000]);assert events==['legacy']
  return dict(case=kind,base=base,passed=True)
 assert result==8 and not events
 assert bytes(u.mem_read(heap,4))==pack(initial)
 call('hbl_batch_read_dispatch',[0x710000]);assert len(events)==1
 response=bytes.fromhex(events[0]);assert response[4:8]==pack(0) and response[8]==({'upload':5,'denied':5,'mask':5,'session':3,'sequence':3,'mismatch':8}.get(kind,0))
 if kind=='upload':assert bytes(u.mem_read(heap,4))==pack(0)
 if kind=='send-failure':assert bytes(u.mem_read(ctx,4))==pack(0)
 call('hbl_batch_read_dispatch',[0x710000]);assert events[-1]=='legacy' and len(events)==2
 if kind.startswith('transition'):
  assert staged
  owned=0x398ea0+({'transition-source':4096,'transition-code':8192,'transition-request':24576}.get(kind,0))
  if kind=='transition-invalid-heap':owned+=4
  u.mem_write(ctx+4,pack(owned));u.mem_write(ctx+8,pack(0 if kind=='transition-locked' else 1))
  target=base if kind=='transition-outside' else owned
  payload2=pack(0x31424248,42,1,2,1,target,0)+pack(0x12345678)
  frame2=b'\xf4\x00\x05\x01'+payload2;frame2+=pack(zlib.crc32(frame2))
  wire2=framed(frame2,0);u.mem_write(0x700000,wire2)
  assert call('original_decode',[0x730000,0x700000,len(wire2),0x710000])==8
  before=bytes(u.mem_read(target,4))
  call('hbl_batch_read_dispatch',[0x710000]);assert len(events)==3
  response2=bytes.fromhex(events[2]);allowed=kind in ('transition-owned','transition-source','transition-code','transition-request')
  assert response2[4:8]==pack(1) and response2[8]==(0 if allowed else 5)
  assert bytes(u.mem_read(target,4))==(pack(0x12345678) if allowed else before)
 return dict(case=kind,base=base,passed=True)
cases=[run(base,kind) for base in (0x2b2880,) for kind in ('upload','compare','maximum','escaped','legacy','control','crc','wire-crc','delimiter','denied','mask','session','sequence','mismatch','send-failure')]
if staged:cases += [run(0x2b2880,kind) for kind in ('transition-owned','transition-source','transition-code','transition-request','transition-locked','transition-invalid-heap','transition-outside')]
report=dict(passed=True,originalFarmLengthFilterExecuted=True,originalRawDecoderExecuted=True,originalCrc16Executed=True,originalSendExecuted=True,cases=cases,hardwareRequests=0,installed=False,adapterSha256=r['sha256'],testSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),abiStubs=['rtos-queue-send','original-read-dispatch','error-log'])
(P/'build/resident-init/transport-arm-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
