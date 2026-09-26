"""固定X1D 1.25.0原厂诊断分发ARM代码模拟；不安装钩子。"""
from pathlib import Path
import sys,hashlib,json
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R3,UC_ARM_REG_R0
out=P/'build/fast-start-research';data=(out/'farm-1.25.0.bin').read_bytes()
assert hashlib.sha256(data).hexdigest()=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
expected={0x94:0x1e0d78,0xd:0x1e0f50,0x1cb:0x1e0ea8,7:0x1e1140,0xc6:0x1e10cc,0xf2:0x1e164c,0xf4:0x1e1768,0x20b:0x1e1888,0x20e:0x1e18cc,0x218:0x1e1920,0x21b:0x1e1964,0x220:0x1e1bc4,0x22d:0x1e1c0c,0x22f:0x1e1c60,0x23e:0x1e1dd4,0x30f:0x1e1e1c,0x4b9:0x1e1e80}
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x100000,0x200000);u.mem_write(0x100000,data)
stops=set(expected.values())|{0x1e22cc};hit=[]
def hook(uc,a,n,ctx):
 if a in stops:hit.append(a);uc.emu_stop()
u.hook_add(UC_HOOK_CODE,hook)
for opcode in range(0x5b1):
 hit.clear();u.reg_write(UC_ARM_REG_R3,opcode);u.emu_start(0x1e20c4,0x1e2400,count=100)
 assert hit==[expected.get(opcode,0x1e22cc)],(opcode,hit)
 if opcode in expected:assert u.reg_read(UC_ARM_REG_R0)==0x6c37f4
report={'passed':True,'opcodesTested':0x5b1,'knownHandlers':len(expected),'firmwareSha256':hashlib.sha256(data).hexdigest(),'installed':False,'hardwareRequests':0,'candidateOpcodeAssigned':False}
(out/'batch-dispatch-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
