"""离线执行固定FARM的原始ROI计算；不导入USB，输出模拟结果供研究复查。"""
import sys,json,struct
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/"x1d/tools"),str(ROOT/".research-cache/x1d-1.25.0/python")]
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC,UC_ARM_REG_CPSR,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_PC
FARM=FarmApplication()
assert FARM.sha256=="317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
PACKED=(39322050,55050870,78644100)

def original_roi(size,point=(5000,5000),dimensions=(2748,468)):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    u.mem_map(0x100000,0x600000);u.mem_write(0x100000,FARM.data)
    u.mem_map(0x900000,0x10000)
    u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
    u.reg_write(UC_ARM_REG_CPSR,0x1f)
    u.mem_write(0x2add4e,struct.pack("<HHHH",*point,*size))
    u.reg_write(UC_ARM_REG_SP,0x90fff0);u.reg_write(UC_ARM_REG_LR,0x900000)
    u.reg_write(UC_ARM_REG_R0,dimensions[0]);u.reg_write(UC_ARM_REG_R1,dimensions[1])
    def hook(v,a,n,_):
        # 固定路径检查/锁入口替身；坐标获取和完整ROI算术使用原始ARM指令。
        if a in (0x21facc,0x236a14):
            v.reg_write(UC_ARM_REG_R0,int(a==0x21facc));v.reg_write(UC_ARM_REG_PC,v.reg_read(UC_ARM_REG_LR))
        elif not (0x1f0090<=a<0x1f0558 or 0x1cd584<=a<0x1cd614):
            raise RuntimeError("unexpected native call "+hex(a))
    u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x1f0090,0x900000,count=2000)
    assert u.reg_read(UC_ARM_REG_PC)==0x900000
    top,left,width,height=struct.unpack("<4H",bytes(u.mem_read(0x6cc59c,8)))
    assert all(v%2==0 for v in (top,left,width,height))
    assert left+width<=dimensions[0] and top+height<=dimensions[1]
    return dict(top=top,left=left,width=width,height=height)

def main():
    output={"method":"offline_original_ARM_with_two_fixed_stubs","farm_sha256":FARM.sha256,
        "entry":"0x1f0090","dimensions":[2748,468],"hardware_requests":0,"results":[]}
    expected=((220,1312,124,28),(214,1288,174,40),(206,1250,248,56))
    for packed,want in zip(PACKED,expected):
        size=(packed&65535,packed>>16)
        for point in ((5000,5000),(0,0),(10000,10000)):
            roi=original_roi(size,point)
            if point==(5000,5000):assert tuple(roi.values())==want
            output["results"].append(dict(packed=packed,size=size,point=point,roi=roi))
    print(json.dumps(output,indent=2))

if __name__=="__main__":main()
