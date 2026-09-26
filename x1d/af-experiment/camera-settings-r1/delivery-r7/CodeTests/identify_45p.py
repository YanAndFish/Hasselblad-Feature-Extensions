"""固定 X1D 1.25.0 的识别表与实际 ARM 匹配回放；仅离线。"""
import sys,json,struct
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path.cwd().resolve()
assert ROOT == Path(__file__).resolve().parents[5]
sys.path[:0]=[str(ROOT/"x1d/tools"),str(ROOT/".research-cache/x1d-1.25.0/python")]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_FP,UC_ARM_REG_SP
f=FarmApplication()
assert f.sha256=="317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
out=Path(__file__).resolve().parent/"output/45p-identity";out.mkdir(parents=True,exist_ok=True)
rows=[]
for index in range(20):
 data=f.read(0x2ad998+36*index,36);name=f.read(struct.unpack_from("<I",data)[0],64).split(b"\0")[0].decode("ascii")
 rows.append(dict(index=index,name=name,match=list(data[5:8]),model=data[4]))
def match(lo,hi,version):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x100000,0x700000);u.mem_map(0x900000,0x10000)
 u.mem_write(f.base,f.data);u.mem_write(0x236a14,bytes.fromhex("0000a0e31eff2fe1"))
 fp=0x908000;u.reg_write(UC_ARM_REG_FP,fp);u.reg_write(UC_ARM_REG_SP,fp-0x2b8)
 for address,value in ((fp-0x2a5,lo),(fp-0x2a6,hi),(fp-5,version),(0x2adc79,19)):u.mem_write(address,bytes([value]))
 def stop(uc,address,size,data):
  if address==0x198cc4:uc.emu_stop()
 u.hook_add(UC_HOOK_CODE,stop);u.emu_start(0x198a84,0,count=100000)
 return u.mem_read(0x2adc79,1)[0]
cases=[]
for triplet,expected in (((55,55,1),1),((55,55,2),19),((55,55,0),19),((55,55,255),19)):
 actual=match(*triplet);assert actual==expected
 cases.append(dict(fields=triplet,model=actual))
report=dict(firmware="X1D 1.25.0",farmSha256=f.sha256,hardwareRequests=0,rows=rows,actualArmCases=cases,
 verified=["Original XCD45 static key is [55,55,1]", "Static matching does not read aperture", "No dedicated 45P static row"],
 pending=["See chain.json for verified actual 45P version and dynamic path", "Independent aperture source and scale remain under investigation"])
(out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
(out/"factory.asm").write_text("\n".join(f.disassembly(a,n) for a,n in ((0x198818,0x54),(0x1988c0,0x460),(0x198d20,0x1e0),(0x1a271c,0x16c))),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
