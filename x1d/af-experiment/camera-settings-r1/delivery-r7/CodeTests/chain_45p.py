"""Actual ARM/Thumb slices across the fixed lens, SUC and FARM; offline only."""
import sys,json,struct
sys.dont_write_bytecode=True
from pathlib import Path
import lens45_reference as lens
import identify_45p as farm
from suc_diagnostic_binary import SucImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
s=SucImage()
# Lens initialization: independent of live calibration, verify normalized focal/version/capability bytes.
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x8000,0x30000);u.mem_write(0x8000,lens.load());u.mem_map(0x20000000,0x10000)
u.mem_write(0x23556,bytes.fromhex("00207047"))
u.reg_write(UC_ARM_REG_R4,0x20006d36);u.reg_write(UC_ARM_REG_R0,0)
u.emu_start(0x1f22d,0x1f2b2,count=1000)
info=bytes(u.mem_read(0x20006d37,16))
assert info[5:7]==bytes([55,55]) and info[13]==2 and info[14]&8
# SUC uses payload[13]&7 as cached lens version, and publishes it in 051c byte4.
v=Uc(UC_ARCH_ARM,UC_MODE_THUMB);v.mem_map(s.base,0x40000);v.mem_write(s.base,s.data);v.mem_map(0x20000000,0x20000)
v.mem_write(0x20010000,info);v.reg_write(UC_ARM_REG_R4,0x20010000)
v.emu_start(0x8009301,0x800930a,count=1000)
assert bytes(v.mem_read(0x20000519,1))==b"\x02"
v.reg_write(UC_ARM_REG_SP,0x2001f000);v.reg_write(UC_ARM_REG_R0,0x20010000)
reply=[]
def sent(uc,a,size,data):
 if a==0x800fba0:
  reply.append(bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0),5)));uc.emu_stop()
v.hook_add(UC_HOOK_CODE,sent);v.emu_start(0x800c735,0,count=1000)
assert len(reply)==1 and struct.unpack_from("<H",reply[0])[0]==0x51c and reply[0][4]==2
triplet=[info[5],info[6],reply[0][4]];assert farm.match(*triplet)==19
# FARM dynamic branch: success consumes lens parameters; failure stays UNKNOWN.
def dynamic(status):
 q=Uc(UC_ARCH_ARM,UC_MODE_ARM);q.mem_map(0x100000,0x700000);q.mem_map(0x900000,0x10000);q.mem_write(farm.f.base,farm.f.data)
 q.mem_write(0x236a14,bytes.fromhex("0000a0e31eff2fe1"));fp=0x908000
 q.reg_write(UC_ARM_REG_FP,fp);q.reg_write(UC_ARM_REG_SP,fp-0x2b8)
 q.mem_write(fp-0x2a5,b"7");q.mem_write(fp-0x2a6,b"7");q.mem_write(0x2adc79,b"\x13")
 # Values are simulated successful parameter response (38 is prior verified lens reference conversion).
 r=bytearray(18);struct.pack_into("<HH",r,4,38,38);r[17]=status;q.mem_write(fp-0x188,bytes(r))
 def stop(uc,a,size,data):
  if a in (0x199220,0x199194):uc.emu_stop()
 q.hook_add(UC_HOOK_CODE,stop);q.emu_start(0x198d20,0,count=10000)
 return q.mem_read(0x2adc79,1)[0]
assert dynamic(0)==18 and dynamic(1)==19
report={"hardwareRequests":0,"lensFirmware":"XCD45P 0.1.36","lensDecodedSha256":lens.SHA,"bodyFirmware":"X1D 1.25.0",
 "farmSha256":farm.f.sha256,"sucSha256":__import__("hashlib").sha256(s.data).hexdigest(),
 "actualLensInit":{"normalizedFocalCodes":triplet[:2],"lensVersion":2,"internalParameterCapability":bool(info[14]&8)},
 "actualSucReplyType":1308,"actualSucReplyVersion":reply[0][4],"actualFarmStaticMatch":19,
 "actualFarmSuccessModel":dynamic(0),"actualFarmFailureModel":dynamic(1),
 "limits":["Offline slices, not live camera observation.","Parameter success/failure reply is simulated; live communication is not verified.","Maximum aperture is not read by the static match loop; its independent field is still being traced."]}
out=Path(__file__).resolve().parent/"output/45p-identity"
(out/"chain.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
(out/"suc.asm").write_text("\n".join(f"{i.address:08x} {i.mnemonic} {i.op_str}" for a,n in ((0x8004054,32),(0x800c734,48),(0x80092f8,30),(0x8009248,60),(0x800d5b8,0xa8)) for i in s.instructions(a,n)),encoding="utf-8")
(out/"lens.asm").write_text("\n".join(lens.dis(a,n) for a,n in ((0x1f1ce,0xe4),(0x1f5d6,0x30),(0x1aa18,0x18))),encoding="utf-8")
print(json.dumps(report))
