"""构建正式功率与同步的固定白名单候选；不连接或安装到设备。"""
from pathlib import Path
import hashlib
import io
import json
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/formal-flash-candidate'
sys.path.insert(0,str(HERE/'research'))
import build_manual_power as power
BASE=power.BASE
CODE=power.CODE
CONTEXT=power.CONTEXT
HEAP=power.HEAP
GROUPS=16
VALUES=82
POWER_WAVES=GROUPS*VALUES
LAMP_BASE=POWER_WAVES
FIRE_INDEX=POWER_WAVES+GROUPS*2

def sha(data): return hashlib.sha256(data).hexdigest()

def frame(index,prefix):
    if not 0<=index<=FIRE_INDEX: raise ValueError('wave index')
    if index==FIRE_INDEX: return prefix+bytes((0xa9,0x50,0xb4,9))
    if index>=LAMP_BASE:
        group,on=divmod(index-LAMP_BASE,2)
        return prefix+bytes((0xa9,0x0a+group if group<6 else group-6,0xd3,on))
    group,value=divmod(index,VALUES)
    return prefix+bytes((0xa9,0x0a+group if group<6 else group-6,0xbc,255 if value==81 else value))

def runs(index,counts,prefix):
    raw=frame(index,prefix)
    return [(count,0,261686886 if raw[i//8]&(1<<(7-i%8)) else 275105382)
            for i,count in enumerate(counts)]

def build(source_override=None):
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('工作区不匹配')
    baseline,counts,lut,prefix=power.inputs()
    OUT.mkdir(exist_ok=True)
    hashes=[power.wave_hash(runs(i,counts,prefix),lut) for i in range(FIRE_INDEX+1)]
    if not all(hashes): raise RuntimeError('zero waveform hash')
    ledger=OUT/'formal_flash_hashes.h'
    ledger.write_text('#ifndef HBL_FORMAL_HASHES_H\n#define HBL_FORMAL_HASHES_H\n'
        f'static const uint32_t hbl_formal_hashes[{FIRE_INDEX+1}]={{\n'+
        ',\n'.join('    '+','.join(f'0x{x:08x}u' for x in hashes[i:i+9]) for i in range(0,len(hashes),9))+
        '\n};\n#endif\n',encoding='ascii')
    hash_path=OUT/'expected-hashes.json'
    hash_path.write_text(json.dumps(hashes)+'\n',encoding='ascii')
    lut_header=OUT/'formal_flash_lut.h'
    lut_header.write_text('#ifndef HBL_FORMAL_LUT_H\n#define HBL_FORMAL_LUT_H\n'
        'static const uint32_t hbl_formal_lut[1024]={\n'+
        ',\n'.join('    '+','.join(f'0x{x:08x}u' for x in lut[i:i+8]) for i in range(0,len(lut),8))+
        '\n};\n#endif\n',encoding='ascii')
    layout=OUT/'firmware.ld'
    layout.write_text('''ENTRY(hbl_formal_dispatch)
SECTIONS {
 . = 0x216b00;
 .text : { KEEP(*(.text*)) *(.rodata*) }
 ASSERT(. <= 0x217f00, "formal firmware overlaps context")
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
''',encoding='ascii')
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name; folder.mkdir(exist_ok=True); env[key]=str(folder)
    source=Path(source_override) if source_override else HERE/'firmware/formal_flash.c'
    elf_path=OUT/'formal-flash.elf'
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    args=[str(compiler),'cc','-target','thumb-freestanding-eabi','-mcpu=cortex_r4','-mfloat-abi=soft',
          '-Os','-g','-fno-lto','-ffunction-sections','-fdata-sections','-ffreestanding',
          '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
          '-fno-pic','-nostdlib','-Wl,--no-undefined','-Wl,--build-id=none',
          '-Wall','-Wextra','-Werror','-I',str(OUT),'-Wl,-T,'+str(layout),str(source),'-o',str(elf_path)]
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode: raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
    sys.path.insert(0,str(HERE/'firmware'))
    from elftools.elf.elffile import ELFFile
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
    from prepared_flash import branch
    elf=ELFFile(io.BytesIO(elf_path.read_bytes()))
    if any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.iter_sections()):
        raise RuntimeError('unresolved firmware relocation')
    section=elf.get_section_by_name('.text'); code=section.data()
    if section['sh_addr']!=CODE or CODE+len(code)>CONTEXT: raise RuntimeError('firmware boundary')
    entries=[int(s['st_value']) for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name=='hbl_formal_dispatch']
    if len(entries)!=1: raise RuntimeError('firmware entry')
    output=bytearray(baseline); output.extend(bytes(HEAP-BASE-len(output)))
    output[CODE-BASE:CODE-BASE+len(code)]=code
    output[0x214400-BASE:0x214404-BASE]=branch(0x214400,entries[0]&~1)
    output[0x1e1838-BASE:0x1e183c-BASE]=struct.pack('<I',HEAP)
    initial=runs(81,counts,prefix)  # 默认 A 组关闭包，发送资格仍为零。
    output[power.RUN_ADDRESS-BASE:power.RUN_ADDRESS-BASE+768]=b''.join(struct.pack('<HHI',*r) for r in initial)
    pointer=0x216980
    if any(baseline[pointer-BASE:pointer-BASE+4]): raise RuntimeError('expected pointer occupied')
    replacement=struct.pack('<HHHH',0xf8df,0x1150,0x6909,0xbf00)
    output[0x21682e-BASE:0x216836-BASE]=replacement
    output[pointer-BASE:pointer-BASE+4]=struct.pack('<I',CONTEXT)
    # 只把旧固定频道比较改为当前受限配置；逐次 PHY 准备、等待、清理原样保留。
    channel_guard=0x216984
    output[0x21684c-BASE:0x216850-BASE]=branch(0x21684c,channel_guard,link=True)
    guard_code=struct.pack('<HHHHHHI',0xf8df,0x1008,0x6a49,0x4770,0xbf00,0xbf00,CONTEXT)
    if any(baseline[channel_guard-BASE:channel_guard-BASE+len(guard_code)]): raise RuntimeError('channel guard occupied')
    output[channel_guard-BASE:channel_guard-BASE+len(guard_code)]=guard_code
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    if [(i.mnemonic,i.op_str) for i in decoder.disasm(replacement,0x21682e)]!=[
            ('ldr.w','r1, [pc, #0x150]'),('ldr','r1, [r1, #0x10]'),('nop','')]:
        raise RuntimeError('fast expected load')
    unchanged=bytearray(output[power.FAST-BASE:power.FAST-BASE+370])
    unchanged[0x2e:0x36]=baseline[power.FAST-BASE+0x2e:power.FAST-BASE+0x36]
    unchanged[0x4c:0x50]=baseline[power.FAST-BASE+0x4c:power.FAST-BASE+0x50]
    if unchanged!=baseline[power.FAST-BASE:power.FAST-BASE+370]: raise RuntimeError('fast side effect change')
    for start,size in [(power.GENERATOR,0xcc),(power.HASH_ROUTINE,0x9e)]:
        if output[start-BASE:start-BASE+size]!=baseline[start-BASE:start-BASE+size]: raise RuntimeError('sample code changed')
    if any(output[CONTEXT-BASE:HEAP-BASE]): raise RuntimeError('nonempty initial context')
    binary=OUT/'formal-wltest.bin'; binary.write_bytes(output)
    manifest={'inputSha256':power.INPUT_SHA,'sha256':sha(output),'bytes':len(output),'entry':entries[0],
              'codeStart':CODE,'codeBytes':len(code),'contextStart':CONTEXT,'heapStart':HEAP,
              'marker':'5854','groupCount':GROUPS,'powerWaves':POWER_WAVES,'controlWaves':FIRE_INDEX,'lampBase':LAMP_BASE,'fireIndex':FIRE_INDEX,
              'holdSelector':26,'releaseSelector':27,'prepareSyncSelector':14,'sendSyncSelector':40,
              'sendPowerSelector':48,'powerConfigBase':512,'targetChannel':5,'targetId':5,
              'channelRange':[1,32],'idRange':[0,99],'idOff':0,'configurationBase':8192,
              'channelGuardAddress':channel_guard,'dynamicExpectedHash':True,
              'initialSendingEnabled':False,'separatePowerAndSyncTypes':True,'perShotPhyPreparation':True,
              'sampleBufferPolicy':'power-batch-overwrites-buffer-restore-and-verify-sync-before-ready',
              'expectedHashesSha256':sha(hash_path.read_bytes()),'elfSha256':sha(elf_path.read_bytes()),
              'sourceHashes':{str(p.relative_to(HERE)).replace('\\','/'):sha(p.read_bytes()) for p in
                  (Path(__file__),source,HERE/'firmware/formal_flash.c',HERE/'native/godox_formal_wave.h',HERE/'native/godox_power_wave.h',ledger,lut_header,Path(power.__file__))},
              'compiler':{'arguments':args,'exit':result.returncode,'stderr':result.stderr},
              'installed':False,'hardwareRequests':0,'physicalTimingVerified':False,'lampReceptionVerified':False}
    (OUT/'firmware-build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest

if __name__=='__main__':
    result=build();print(json.dumps({k:result[k] for k in ('codeBytes','powerWaves','sha256','installed','hardwareRequests')}))
