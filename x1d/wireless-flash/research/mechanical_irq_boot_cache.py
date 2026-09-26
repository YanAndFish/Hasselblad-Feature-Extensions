"""核对原包 FSBL 是否初始化运行态 PCAP 缓存；只处理固定官方输入。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'

def replay_cache(fsbl,boot):
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn import arm_const as arm
    table=struct.unpack_from('<I',boot,0x9c)[0]
    header=boot[table+64:table+128]
    words=struct.unpack('<16I',header)
    assert sum(words)&0xffffffff==0xffffffff and words[6]==0x20 and words[0]==words[1]==words[2]
    start,size=words[5]*4,words[0]*4
    assert size==5979936
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for a,n in ((0,0x20000),(0x3000000,0x20000),(0x2129000,(64+size+4095)&~4095)):
        u.mem_map(a,n)
    u.mem_write(0,fsbl); u.mem_write(0x3010100,header)
    for a,v in ((0x1d060,0),(0x1d0d9,0),(0x1d0cc,0),(0x1d0da,0),(0x1d0e0,1)):
        u.mem_write(a,bytes([v]))
    u.mem_write(0x1d0d0,struct.pack('<I',0x3010000))
    u.mem_write(0x3010000,bytes.fromhex('1eff2fe1'))
    calls=[]
    def code(uc,a,n,_):
        if a==0x3010000:
            args=[uc.reg_read(getattr(arm,'UC_ARM_REG_R'+str(i))) for i in range(3)]
            assert args==[start,0x2129040,size],args
            calls.append(args); uc.mem_write(args[1],boot[start:start+size])
            uc.reg_write(arm.UC_ARM_REG_R0,0)
            uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,code)
    u.reg_write(arm.UC_ARM_REG_CPSR,0x60000153)
    u.reg_write(arm.UC_ARM_REG_SP,0x3008000)
    u.reg_write(arm.UC_ARM_REG_R0,0); u.reg_write(arm.UC_ARM_REG_R1,0x3010100)
    u.emu_start(0xbdc,0xd28,count=1000)
    assert u.reg_read(arm.UC_ARM_REG_PC)==0xd28 and len(calls)==1
    assert struct.unpack('<II',u.mem_read(0x2129004,8))==(size,0x2129040)
    cached=bytes(u.mem_read(0x2129040,size))
    assert hashlib.sha256(cached).hexdigest()=='8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30'
    return {'passed':True,'actualFsblInstructions':True,'storageReadModeled':True,
        'plBranchFlagIsSyntheticInput':True,'headerFromOriginalPlPartition':True,
        'descriptorAddress':'0x02129000','imageAddress':'0x02129040','imageEnd':'0x026dcf60',
        'bytes':size,'cachedSha256':hashlib.sha256(cached).hexdigest(),
        'configurationOrBootActuallyExecuted':False,'hardwareRequests':0}

def run():
    assert Path.cwd().resolve()==ROOT
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import HASHES
    from binary import Cs,CS_ARCH_ARM,CS_MODE_ARM,CS_MODE_LITTLE_ENDIAN
    spec=importlib.util.spec_from_file_location('irq_cache_boot_input',ROOT/'x1d/recovery-review/20260910-usb-sd/inspect_payloads.py')
    reader=importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)
    reader.WANTED=set(HASHES); inputs=reader.inputs()
    for name,digest in HASHES.items(): assert hashlib.sha256(inputs[name]).hexdigest()==digest
    even=next(v for n,v in inputs.items() if 'bootimage_even' in n)
    odd=next(v for n,v in inputs.items() if 'bootimage_odd' in n)
    spread=[sum(((v>>bit)&1)<<(2*bit) for bit in range(8)) for v in range(256)]
    boot=b''.join((spread[e]|spread[o]<<1).to_bytes(2,'big') for e,o in zip(even,odd))
    assert hashlib.sha256(boot).hexdigest()=='96449fce1e2bd5d9f181e92d84704154f97f3a758a5adeac11b466cc023f82f5'
    fsbl=boot[0x1700:0x1700+0x1c014]
    assert struct.unpack_from('<III',boot,0x30)==(0x1700,0x1c014,0)
    decoder=Cs(CS_ARCH_ARM,CS_MODE_ARM|CS_MODE_LITTLE_ENDIAN); decoder.skipdata=True
    instructions=list(decoder.disasm(fsbl,0))
    refs=[i.address for i in instructions if
          (i.mnemonic.startswith(('mov','add')) and any(x in i.op_str for x in ('#0x212','#0x2100000','#0x29000')))]
    literals=[i for i in range(0,len(fsbl)-3,4) if struct.unpack_from('<I',fsbl,i)[0] in (0x2100000,0x2129000,0x2129004,0x2129008)]
    excerpts=[]
    for a in sorted(set(refs+literals)):
        start=max(0,a-24); end=min(len(fsbl),a+64)
        excerpts.append({'address':hex(a),'instructions':[
            {'address':hex(i.address),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str}
            for i in decoder.disasm(fsbl[start:end],start)]})
    report={'firmware':'X1D 1.25.0','hardwareRequests':0,'fsblSha256':hashlib.sha256(fsbl).hexdigest(),
        'candidateReferences':excerpts,'runtimePointerRead':False,
        'cacheReplay':replay_cache(fsbl,boot),
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'boot-cache-search.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # 原始固件提取字节只写入已忽略的构建目录，供后续离线反汇编。
    (OUT/'original-fsbl.bin').write_bytes(fsbl)
    return report

if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False))
