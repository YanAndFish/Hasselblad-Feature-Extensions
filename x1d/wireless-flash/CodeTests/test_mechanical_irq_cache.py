"""真实 C 完整哈希、每个差量中断点的恢复，以及 ARM 整图分类回放。"""
from pathlib import Path
import ctypes as c
import hashlib
import json
import struct
import sys
import time

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'
sys.path.insert(0,str(HERE/'research'))
from mechanical_irq_loading import apply_image

def run():
    assert Path.cwd().resolve()==ROOT
    plan=json.loads((OUT/'irq-pl-word-plan.json').read_text(encoding='utf-8'))
    build=json.loads((OUT/'irq-cache-build.json').read_text(encoding='utf-8'))
    for name,digest in build['sourceHashes'].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest
    assert hashlib.sha256((OUT/'irq-cache.dll').read_bytes()).hexdigest()==build['dllSha256']
    candidate=(OUT/'irq-pl-candidate.bin').read_bytes(); original=apply_image(candidate,plan,True)
    lib=c.CDLL(str(OUT/'irq-cache.dll'))
    classify=lib.mechanical_irq_cache_classify; change=lib.mechanical_irq_cache_change
    classify.argtypes=[c.c_void_p,c.c_uint32]; classify.restype=c.c_uint32
    change.argtypes=[c.c_void_p,c.c_uint32,c.c_uint32,c.c_uint32]; change.restype=c.c_uint32
    n=len(original); buf=(c.c_uint32*(n//4))(); c.memmove(buf,original,n)
    assert classify(buf,n)==0
    assert change(buf,n,1,253)==0 and bytes(buf)==candidate and classify(buf,n)==1
    assert change(buf,n,2,253)==0 and bytes(buf)==original
    assert classify(None,n)==3 and classify(buf,n-4)==3 and classify(c.addressof(buf)+1,n)==3
    assert change(buf,n,0,253)==5 and bytes(buf)==original
    # 所有 254 个可中断前缀都来自实际机器 C 写入；未知状态不能继续应用。
    for budget in range(254):
        c.memmove(buf,original,n)
        result=change(buf,n,1,budget)
        assert result==(0 if budget==253 else 4)
        expected=0 if budget==0 else 1 if budget==253 else 2
        assert classify(buf,n)==expected
        if expected==2:
            snapshot=bytes(buf); assert change(buf,n,1,253)==5 and bytes(buf)==snapshot
        assert change(buf,n,2,253)==0 and bytes(buf)==original
    # 不仅连续前缀：非连续混合态也能逐字还原；任意未知字均在写入前拒绝。
    for i,row in enumerate(plan['words']):
        if i%3==0: buf[row['offset']//4]=row['after']
    assert classify(buf,n)==2 and change(buf,n,2,253)==0 and bytes(buf)==original
    for offset in (0,n//2,n-4,plan['words'][0]['offset'],plan['words'][-1]['offset']):
        c.memmove(buf,original,n); buf[offset//4]^=1; snapshot=bytes(buf)
        # 差量字的 1-bit 翻转可能恰是候选值，因此挑选两种已知值之外的字。
        row=next((r for r in plan['words'] if r['offset']==offset),None)
        if row and buf[offset//4] in (row['before'],row['after']): buf[offset//4]^=0x80000000; snapshot=bytes(buf)
        assert classify(buf,n)==3
        for action in (1,2): assert change(buf,n,action,253)==5 and bytes(buf)==snapshot
    host={'passed':True,'interruptionPrefixes':254,'fullForwardReverseExact':True,'immutableCorruptionRejected':True}
    print(json.dumps({'hostCacheValidation':host}),flush=True)
    # 执行真实目标 ARM 全图 SHA，外部库不替代哈希函数。
    sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_PROT_READ,UC_PROT_ALL
    from unicorn import arm_const as arm
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM); payload=(OUT/'irq-cache.bin').read_bytes()
    assert hashlib.sha256(payload).hexdigest()==build['sha256']
    u.mem_map(build['base']&~4095,0x3000);u.mem_write(build['base'],payload)
    address=0x2129040; first=address&~4095; size=(address-first+n+4095)&~4095
    u.mem_map(first,size,UC_PROT_ALL);u.mem_write(address,original);u.mem_protect(first,size,UC_PROT_READ)
    u.mem_map(0x3000000,0x8000)
    u.reg_write(arm.UC_ARM_REG_CPSR,0x60000013)
    u.reg_write(arm.UC_ARM_REG_SP,0x3007000);u.reg_write(arm.UC_ARM_REG_LR,0x3200000)
    u.reg_write(arm.UC_ARM_REG_R0,address);u.reg_write(arm.UC_ARM_REG_R1,n)
    start=time.monotonic();u.emu_start(build['entries']['mechanical_irq_cache_classify'],0x3200000,count=500000000)
    assert u.reg_read(arm.UC_ARM_REG_PC)==0x3200000 and u.reg_read(arm.UC_ARM_REG_R0)==0
    report={'passed':True,'installed':False,'hardwareRequests':0,'host':host,
        'armFullBaselineShaExecuted':True,'armCacheReadOnlyProtection':True,
        'armReplayHostSeconds':round(time.monotonic()-start,3),'notDeviceTiming':True,
        'payloadSha256':build['sha256'],'sourceHashes':{str(Path(__file__).relative_to(HERE)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    (OUT/'irq-cache-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False))
