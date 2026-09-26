"""独立构建芯片预准备实验件，不改现有安装包、不访问设备。"""
from pathlib import Path
import hashlib, json, os, struct, subprocess, sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-hw-ready-candidate'
BASE=0x180000
CODE=0x216b00
CONTEXT=0x217f00
HEAP=0x218000
INPUT_SHA='654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688'

def sha(data): return hashlib.sha256(data).hexdigest()

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    source=HERE/'firmware/mechanical_hw_ready.c'
    baseline=(HERE/'build/prepared-wltest.bin').read_bytes()
    if sha(baseline)!=INPUT_SHA: raise RuntimeError('Fixed firmware changed')
    OUT.mkdir(exist_ok=True)
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        p=OUT/name; p.mkdir(exist_ok=True); env[key]=str(p)
    layout=OUT/'layout.ld'
    layout.write_text('''ENTRY(hbl_hw_prepare)
SECTIONS {
 . = 0x216b00;
 .text : { KEEP(*(.text*)) *(.rodata*) }
 ASSERT(. <= 0x217f00, "code overlaps saved context")
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
''',encoding='ascii')
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    elfpath=OUT/'hardware-ready.elf'
    args=[str(compiler),'cc','-target','thumb-freestanding-eabi','-mcpu=cortex_r4','-mfloat-abi=soft',
          '-Os','-g','-fno-lto','-ffunction-sections','-fdata-sections','-ffreestanding',
          '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
          '-fno-pic','-nostdlib','-Wl,--no-undefined','-Wl,--build-id=none',
          '-Wall','-Wextra','-Werror','-Wl,-T,'+str(layout),str(source),'-o',str(elfpath)]
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode: raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
    from elftools.elf.elffile import ELFFile
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
    import io
    elf=ELFFile(io.BytesIO(elfpath.read_bytes()))
    if any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.iter_sections()):
        raise RuntimeError('Unexpected relocations')
    text=elf.get_section_by_name('.text'); code=text.data()
    if text['sh_addr']!=CODE or CODE+len(code)>CONTEXT: raise RuntimeError('Invalid code layout')
    symbols={s.name:int(s['st_value']) for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name.startswith('hbl_hw_')}
    if set(symbols)!=set(('hbl_hw_prepare','hbl_hw_fire','hbl_hw_release')): raise RuntimeError('Wrong entries')
    sys.path.insert(0,str(HERE/'firmware'))
    from prepared_flash import branch,mov16
    output=bytearray(baseline); output.extend(bytes(HEAP-BASE-len(output)))
    output[CODE-BASE:CODE-BASE+len(code)]=code
    output[0x214404-BASE:0x214408-BASE]=mov16(0,0x5850)
    output[0x2145fe-BASE:0x214602-BASE]=branch(0x2145fe,symbols['hbl_hw_release']&~1)
    # 40 消费已准备资格发射；41 只完成内部准备。27 配对解除芯片准备与 MAC 占用。
    entry=0x2146a8
    dispatch=struct.pack('<HH',0x2928,0xd101)+branch(entry+4,symbols['hbl_hw_fire']&~1)
    dispatch+=struct.pack('<HH',0x2929,0xd101)+branch(entry+12,symbols['hbl_hw_prepare']&~1)
    dispatch+=branch(entry+16,0x1c620e)
    output[entry-BASE:entry-BASE+len(dispatch)]=dispatch
    output[0x1e1838-BASE:0x1e183c-BASE]=struct.pack('<I',HEAP)
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    decoded=list(decoder.disasm(dispatch,entry))
    if decoded[1].op_str!='#0x2146b0' or decoded[4].op_str!='#0x2146b8':
        raise RuntimeError('Dispatch branch mismatch')
    disassembly='\n'.join(hex(i.address)+' '+i.mnemonic+' '+i.op_str for i in decoder.disasm(code,CODE))+'\n'
    (OUT/'hardware-ready.disasm.txt').write_text(disassembly,encoding='ascii')
    path=OUT/'hardware-ready-wltest.bin'; path.write_bytes(output)
    manifest={'inputSha256':INPUT_SHA,'sha256':sha(output),'bytes':len(output),'symbols':symbols,
              'codeStart':CODE,'codeBytes':len(code),'contextStart':CONTEXT,'heapStart':HEAP,
              'marker':'5850','prepareSelector':41,'fireSelector':40,'releaseSelector':27,
              'sourceSha256':sha(source.read_bytes()),'buildScriptSha256':sha(Path(__file__).read_bytes()),
              'waveformBytesUnchanged':output[0x214800-BASE:0x215f00-BASE]==baseline[0x214800-BASE:0x215f00-BASE],
              'installed':False,'packagedForHardware':False,'hardwareRequests':0,
              'physicalReadyRetentionVerified':False,'physicalEmissionDuringPrepareVerified':False,
              'compiler':{'arguments':args,'stderr':result.stderr,'exit':result.returncode}}
    if not manifest['waveformBytesUnchanged']: raise RuntimeError('Waveform changed')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:manifest[k] for k in ('codeBytes','sha256','waveformBytesUnchanged','installed','hardwareRequests')}

if __name__=='__main__': print(build())
