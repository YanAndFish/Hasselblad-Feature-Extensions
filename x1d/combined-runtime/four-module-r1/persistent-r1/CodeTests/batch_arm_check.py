"""执行候选接收器ARM指令，内存与授权回调为替身。"""
from pathlib import Path
import sys,os,struct,json,subprocess,io,hashlib
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
out=P/'build/batch-model';env=dict(os.environ)
for k,n in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:env[k]=str(out/n)
layout=out/'receiver.ld';layout.write_text('SECTIONS { . = 0x20000; .text : { *(.text*) } .rodata : { *(.rodata*) } .ARM.exidx : { *(.ARM.exidx*) } }',encoding='utf-8')
elfpath=out/'receiver.elf'
subprocess.run([str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-marm','-Oz','-ffreestanding','-nostdlib','-Wl,-T,'+str(layout),'-Wl,-e,hbl_batch_receive',str(P/'native/boot_batch_receiver.c'),'-o',str(elfpath)],env=env,check=True)
e=ELFFile(io.BytesIO(elfpath.read_bytes()))
def run(kind,op,count):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x10000,0x100000)
 for seg in e.iter_segments():
  if seg['p_type']=='PT_LOAD':u.mem_write(seg['p_vaddr'],seg.data())
 pack=lambda *v:struct.pack('<'+'I'*len(v),*v)
 p=pack(0x31424248,42,0,op,count,0x300000 if op==2 else 0,0)
 for i in range(count):p+=pack(0x300000+i*4,i,0xffffffff) if op==1 else pack(i)
 if kind=='truncated':p=p[:-1]
 u.mem_write(0x50000,pack(42,0,0));u.mem_write(0x50100,pack(0,0x60000,0x60004,0x60008));u.mem_write(0x51000,p)
 seen=[];mem={0x300000+i*4:i for i in range(count)}
 def hook(m,a,n,c):
  if a not in (0x60000,0x60004,0x60008):return
  target=m.reg_read(UC_ARM_REG_R1);val=m.reg_read(UC_ARM_REG_R2);ok=1
  if a==0x60000:
   target=val;ok=int(target in mem and not(kind=='denied-last' and target==0x300000+4*(count-1)))
  elif a==0x60004:
   seen.append(('read',target));m.mem_write(val,pack(mem[target]^(1 if kind=='mismatch' else 0)))
   if kind=='read-failed':ok=0
  else:seen.append(('write',target));mem[target]=val
  m.reg_write(UC_ARM_REG_R0,ok);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 for reg,val in [(UC_ARM_REG_R0,0x50000),(UC_ARM_REG_R1,0x50100),(UC_ARM_REG_R2,0x51000),(UC_ARM_REG_R3,len(p)),(UC_ARM_REG_SP,0x10fff0),(UC_ARM_REG_LR,0x70000)]:u.reg_write(reg,val)
 u.emu_start(e['e_entry'],0x70000,count=100000)
 assert u.reg_read(UC_ARM_REG_PC)==0x70000
 result=u.reg_read(UC_ARM_REG_R0);assert (result==0)==(kind=='normal')
 if kind in ('truncated','denied-last'):assert not seen
 if kind in ('read-failed','mismatch'):assert len(seen)==(2 if op==2 else 1)
 state=struct.unpack('<III',u.mem_read(0x50000,12));assert state==(42,1,0) if kind=='normal' else state==(42,0,1)
 return dict(case=kind,operation=op,count=count,result=result,accesses=len(seen))
cases=[run(k,op,20 if op==1 else 60) for op in (1,2) for k in ('normal','truncated','denied-last','read-failed','mismatch')]
r=dict(passed=True,cases=cases,hardwareRequests=0,installed=False,elfSha256=hashlib.sha256(elfpath.read_bytes()).hexdigest())
(out/'arm-validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
