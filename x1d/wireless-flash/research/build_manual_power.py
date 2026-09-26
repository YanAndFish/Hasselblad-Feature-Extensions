"""固定无线基线上生成独立功率候选；只读输入、离线构建，不访问设备。"""
from pathlib import Path
import hashlib
import io
import json
import os
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/manual-power-candidate'
BASE=0x180000
CODE=0x216b00
CONTEXT=0x217f00
HEAP=0x218000
INPUT_SHA='654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688'
GENERATOR=0x214800
HASH_ROUTINE=0x214a00
RUN_ADDRESS=0x215c00
FAST=0x216800


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inputs():
    blob=(HERE/'build/prepared-wltest.bin').read_bytes()
    if sha(blob)!=INPUT_SHA:
        raise RuntimeError('固定无线波形基线发生变化')
    runs=[struct.unpack_from('<HHI',blob,RUN_ADDRESS-BASE+8*i) for i in range(96)]
    steps=sorted({item[2] for item in runs})
    if steps!=[261686886,275105382]:
        raise RuntimeError('固定调制步进不匹配')
    counts=[item[0] for item in runs]
    if counts!=[160+(i in (0,25,51,76)) for i in range(96)] or any(item[1] for item in runs):
        raise RuntimeError('固定采样长度不匹配')
    bits=[int(item[2]==steps[0]) for item in runs]
    frame=bytes(sum(bits[i+j]<<(7-j) for j in range(8)) for i in range(0,96,8))
    prefix=b'\xaa'*4+(0xc368//6).to_bytes(2,'big')*2
    if frame!=prefix+bytes((0xa9,0x0d,0xb4,9)):
        raise RuntimeError('原固定普通包不匹配')
    lut=struct.unpack_from('<1024I',blob,0x214c00-BASE)
    if wave_hash(runs,lut)!=0x0e77be41:
        raise RuntimeError('独立模型未复现原波形校验值')
    return blob,counts,lut,prefix


def power_runs(group,value,counts,prefix):
    if group not in range(5) or value not in range(81):
        raise ValueError('功率或组范围错误')
    frame=prefix+bytes((0xa9,0x0a+group,0xbc,value))
    return [(count,0,261686886 if frame[i//8]&(1<<(7-i%8)) else 275105382)
            for i,count in enumerate(counts)]


def wave_hash(runs,lut):
    value=0x811c9dc5
    phase=0
    for _ in range(256):
        value=value*0x01000193&0xffffffff
    for samples,_,step in runs:
        for _ in range(samples):
            phase=(phase+step)&0xffffffff
            value=(value^lut[phase>>22])*0x01000193&0xffffffff
    for _ in range(0x31fc):
        value=value*0x01000193&0xffffffff
    return value


def build():
    if Path.cwd().resolve()!=ROOT:
        raise RuntimeError('工作区不匹配')
    baseline,counts,lut,prefix=inputs()
    OUT.mkdir(exist_ok=True)
    hashes=[wave_hash(power_runs(group,value,counts,prefix),lut)
            for group in range(5) for value in range(81)]
    if not all(hashes):
        raise RuntimeError('无效的零校验值')
    header=OUT/'godox_power_hashes.h'
    header.write_text('#ifndef HBL_GODOX_POWER_HASHES_H\n#define HBL_GODOX_POWER_HASHES_H\n'
        'static const uint32_t hbl_power_expected_hashes[405]={\n'+
        ',\n'.join('    '+','.join(f'0x{x:08x}u' for x in hashes[i:i+9]) for i in range(0,405,9))+
        '\n};\n#endif\n',encoding='ascii')
    (OUT/'expected-hashes.json').write_text(json.dumps(hashes)+'\n',encoding='ascii')
    layout=OUT/'layout.ld'
    layout.write_text('''ENTRY(hbl_power_dispatch)
SECTIONS {
 . = 0x216b00;
 .text : { KEEP(*(.text*)) *(.rodata*) }
 ASSERT(. <= 0x217f00, "power code overlaps context")
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
''',encoding='ascii')
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),
                     ('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name
        folder.mkdir(exist_ok=True)
        env[key]=str(folder)
    source=HERE/'firmware/manual_power.c'
    elfpath=OUT/'manual-power.elf'
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    args=[str(compiler),'cc','-target','thumb-freestanding-eabi','-mcpu=cortex_r4','-mfloat-abi=soft',
          '-Os','-g','-fno-lto','-ffunction-sections','-fdata-sections','-ffreestanding',
          '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
          '-fno-pic','-nostdlib','-Wl,--no-undefined','-Wl,--build-id=none',
          '-Wall','-Wextra','-Werror','-I',str(OUT),'-Wl,-T,'+str(layout),str(source),'-o',str(elfpath)]
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
    sys.path.insert(0,str(HERE/'firmware'))
    from elftools.elf.elffile import ELFFile
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
    from prepared_flash import branch
    elf=ELFFile(io.BytesIO(elfpath.read_bytes()))
    if any(section['sh_type'] in ('SHT_REL','SHT_RELA') and section['sh_size'] for section in elf.iter_sections()):
        raise RuntimeError('存在未解决的重定位')
    section=elf.get_section_by_name('.text')
    code=section.data()
    if section['sh_addr']!=CODE or CODE+len(code)>CONTEXT:
        raise RuntimeError('候选代码越界')
    symbols={symbol.name:int(symbol['st_value']) for symbol in elf.get_section_by_name('.symtab').iter_symbols()
             if symbol.name=='hbl_power_dispatch'}
    if set(symbols)!={'hbl_power_dispatch'}:
        raise RuntimeError('候选入口不匹配')
    output=bytearray(baseline)
    output.extend(bytes(HEAP-BASE-len(output)))
    output[CODE-BASE:CODE-BASE+len(code)]=code
    output[0x214400-BASE:0x214404-BASE]=branch(0x214400,symbols['hbl_power_dispatch']&~1)
    output[0x1e1838-BASE:0x1e183c-BASE]=struct.pack('<I',HEAP)
    # 默认数据也只含功率命令；未显式 hold/configure 时始终不具备发送资格。
    initial=power_runs(3,0,counts,prefix)
    output[RUN_ADDRESS-BASE:RUN_ADDRESS-BASE+768]=b''.join(struct.pack('<HHI',*run) for run in initial)
    # FAST 的其余准备、状态检查、500 等待及清理保持固定输入字节。
    # 仅把 r1 的固定旧哈希加载换成 CONTEXT.expected_hash 的真实动态值。
    pointer=0x216980
    if any(baseline[pointer-BASE:pointer-BASE+4]):
        raise RuntimeError('校验指针槽不为空')
    replacement=struct.pack('<HHHH',0xf8df,0x1150,0x6909,0xbf00)
    output[0x21682e-BASE:0x216836-BASE]=replacement
    output[pointer-BASE:pointer-BASE+4]=struct.pack('<I',CONTEXT)
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    actual=[(item.mnemonic,item.op_str) for item in decoder.disasm(replacement,0x21682e)]
    if actual!=[('ldr.w','r1, [pc, #0x150]'),('ldr','r1, [r1, #0x10]'),('nop','')]:
        raise RuntimeError('动态校验加载的指令不匹配')
    unchanged_fast=bytearray(output[FAST-BASE:FAST-BASE+370])
    unchanged_fast[0x2e:0x36]=baseline[FAST-BASE+0x2e:FAST-BASE+0x36]
    if unchanged_fast!=baseline[FAST-BASE:FAST-BASE+370]:
        raise RuntimeError('原发送控制流程发生额外改变')
    if output[GENERATOR-BASE:GENERATOR-BASE+0xcc]!=baseline[GENERATOR-BASE:GENERATOR-BASE+0xcc] or \
       output[HASH_ROUTINE-BASE:HASH_ROUTINE-BASE+0x9e]!=baseline[HASH_ROUTINE-BASE:HASH_ROUTINE-BASE+0x9e]:
        raise RuntimeError('原样本生成或读回校验函数发生改变')
    if any(output[CONTEXT-BASE:HEAP-BASE]):
        raise RuntimeError('初始运行上下文不为空')
    path=OUT/'manual-power-wltest.bin'
    path.write_bytes(output)
    manifest={'inputSha256':INPUT_SHA,'sha256':sha(output),'bytes':len(output),'symbols':symbols,
              'codeStart':CODE,'codeBytes':len(code),'contextStart':CONTEXT,'heapStart':HEAP,
              'marker':'5852','holdSelector':26,'releaseSelector':27,'sendPowerSelector':48,
              'configSelectorBase':512,'configValues':405,'targetChannel':5,'targetId':5,
              'command':'manual-output-power','ordinaryFlashCommandExposed':False,
              'initialSendingEnabled':False,'lookupTableUnchanged':True,
              'sampleCount':0x6f00,'modulatedSamples':sum(counts),'fastControlFlowPreserved':True,
              'installed':False,'packagedForHardware':False,'hardwareRequests':0,
              'lampReceptionVerified':False,'physicalPowerVerified':False,
              'sourceHashes':{str(item.relative_to(HERE)).replace('\\','/'):sha(item.read_bytes()) for item in
                             (Path(__file__),source,HERE/'native/godox_power_wave.h',HERE/'native/godox_manual_power.h',header)},
              'elfSha256':sha(elfpath.read_bytes()),'expectedHashesSha256':sha((OUT/'expected-hashes.json').read_bytes()),
              'compiler':{'arguments':args,'exit':result.returncode,'stderr':result.stderr}}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {key:manifest[key] for key in ('codeBytes','sha256','configValues','installed','hardwareRequests')}


if __name__=='__main__':
    print(json.dumps(build(),ensure_ascii=False))
