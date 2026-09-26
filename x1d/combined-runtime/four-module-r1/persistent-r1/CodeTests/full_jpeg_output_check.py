"""固定 ARM 质量路径及集成输出清单；不接触相机或照片。"""
import sys, importlib.util, json, struct, hashlib, unittest
from pathlib import Path
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
sys.path.insert(0,str(P));sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
import build_full_jpeg_output as package
from binary import ArmElf
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import *

config,jpeg,meta=package.components()
e=ArmElf(jpeg)
checks=[]
def machine():
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x10000,0x50000)
 for s in e.elf.iter_segments():
  if s['p_type']=='PT_LOAD':u.mem_write(s['p_vaddr'],s.data())
 u.mem_map(0x60000000,0x20000)
 return u
for q in [0,50,85,92,100,255]:
 u=machine();u.reg_write(UC_ARM_REG_R3,q)
 u.emu_start(0x22490,0x22494)
 assert u.reg_read(UC_ARM_REG_R7)==85
 u.reg_write(UC_ARM_REG_R4,0x60001000)
 u.emu_start(0x2255c,0x22560)
 assert struct.unpack('<I',u.mem_read(0x60001054,4))[0]==85
 u.reg_write(UC_ARM_REG_SP,0x60018000)
 u.emu_start(0x247e8,0x24810)
 assert struct.unpack('<I',u.mem_read(0x60018000,4))[0]==30 # 200-2*85
checks.append('实际 ARM 构造质量覆盖、worker 字段及量化比例 30，六种输入')
# 原始量化计算，包含 zigzag 索引与 1..255 饱和，独立公式逐字节对照。
for scale in [16,30]: # 原厂 Q92 与候选 Q85
 u=machine();u.reg_write(UC_ARM_REG_SP,0x60018000);u.reg_write(UC_ARM_REG_LR,0x50000)
 u.reg_write(UC_ARM_REG_R1,0x60002000);u.reg_write(UC_ARM_REG_R2,0x60003000);u.reg_write(UC_ARM_REG_R3,64)
 values=bytes([0,1,2,5,10,20,80,255]*8);u.mem_write(0x60003000,values)
 u.mem_write(0x60018000,struct.pack('<I',scale))
 u.emu_start(0x238c8,0x50000)
 indexaddr=(0x238f0+8+e.word(0x23938)+0x48)&0xffffffff
 order=[0]+list(e.read(indexaddr+1,63))
 expected=bytes(max(1,min(255,(values[i]*scale+50)//100)) for i in order)
 assert bytes(u.mem_read(0x60002000,64))==expected
checks.append('实际 ARM 量化表与独立公式逐字节一致')
# 在包含质量修改的最终 JPEG 二进制上重跑既有成功、失败与队列释放用例。
spec=importlib.util.spec_from_file_location('jpeg_paths',ROOT/'x1d/CodeTests/jpeg_failure/test_arm_path.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
old=m.build
def combined(source=None):
 if source is not None:old(source) # 保留基线拒绝检查
 return jpeg,dict(meta['jpegFailure'],candidateSha256=package.sha(jpeg))
m.build=combined
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(m.JpegFailureTests))
assert result.wasSuccessful()
checks.append('最终编码组件通过原错误处理的六个测试方法')
p=package.build();out=P/'build/full-jpeg-output';stage=out/'stage'
prior=(P/'build/focus-delivery-repair/stage/files/manifest.sha256').read_text()
def entries(s):return dict((line.split('  ',1)[1],line.split('  ',1)[0]) for line in s.splitlines())
a=entries(prior);b=entries((stage/'files/manifest.sha256').read_text())
assert all(b[n]==h for n,h in a.items() if n!='baseline.sha256')
assert set(b)-set(a)=={'configstore-full','jpeg-daemon-full','full-jpeg-config.conf','full-jpeg-encoder.conf'}
assert b['af-ui.rcc']==a['af-ui.rcc'] and b['libhbl-af-ui.so']==a['libhbl-af-ui.so']
checks.append('原整包 UI、RAW 回放、拖动、无线、FARM 均逐项保持原哈希')
proof=dict(passed=True,packageSha256=p['packageSha256'],checks=checks,
    actualEncodingMeasured=False,targetSizeMeasured=False,hardwareRequests=0)
(out/'validation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False))
