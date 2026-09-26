"""构建仅用于独立图片预览进程的驻留显隐回调，并模拟原始 ARM64 指令。"""
import hashlib, json, struct, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
D = Path(__file__).resolve().parent
FAST = '--fast' in sys.argv
OUT = D / 'native-input-candidate' if FAST else D
INTERVAL = 5 if FAST else 20
sys.path[:0] = [str(ROOT/'.research-cache/python'), str(ROOT/'.research-cache/x1d-1.25.0/python'), str(ROOT/'x2d/tools')]
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *
from firmware_image import system_elf
SHA='16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0'
CAVE=0xad76c8
HOOK=0x333fc0
with (OUT/'resident_page.o').open('rb') as f:
    elf=ELFFile(f); blob=bytearray(elf.get_section_by_name('.text').data())
    symbols=elf.get_section_by_name('.symtab')
    mailbox=next(s['st_value'] for s in symbols.iter_symbols() if s.name=='resident_mailbox')
    for sec in elf.iter_sections():
        if sec['sh_type']!='SHT_RELA': continue
        assert sec.name=='.rela.text'
        for r in sec.iter_relocations():
            assert r['r_info_type']==274, 'Only ADR relocations reviewed'
            off=r['r_offset']; delta=symbols.get_symbol(r['r_info_sym'])['st_value']+r['r_addend']-off
            assert -(1<<20)<=delta<(1<<20)
            word=struct.unpack_from('<I',blob,off)[0]
            assert word&0x9f000000==0x10000000
            word=(word&~((3<<29)|(0x7ffff<<5)))|((delta&3)<<29)|(((delta>>2)&0x7ffff)<<5)
            struct.pack_into('<I',blob,off,word)
assert len(blob)<=1544
b=system_elf('/bin/camera-gui',SHA)
assert b.read(HOOK,4)==bytes.fromhex('1f040071')
branch=struct.pack('<I',0x14000000|(((CAVE-HOOK)//4)&0x3ffffff))
cases=[]
for mode,desired,applied,windows in [(1,0,255,1),(1,1,0,1),(1,0,1,1),(1,1,1,1),(1,0,255,0),(1,1,255,2),(1,2,1,1),(0,0,0,1),(2,0,0,1)]:
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM); base=0x40000000
    u.mem_map(base,0x2300000);u.mem_map(0x70000000,0x10000)
    u.mem_write(base+CAVE,bytes(blob));u.mem_write(base+HOOK,branch)
    box=base+CAVE+mailbox;u.mem_write(box,bytes([desired,applied,0,0]))
    u.mem_write(base+0x21cf850,struct.pack('<QQQ',0,0x70000100,windows))
    u.mem_write(0x70000100,struct.pack('<Q',0x70000200))
    calls=[]
    names={0x219498:'delete',0x2194e8:'new',0xb45400:'visible',0xb45a70:'isvisible',0x901ea8:'schedule',0x8c2410:'quit'}
    def stub(uc,address,size,data):
        name=names.get(address-base)
        if name is None:return
        x0=uc.reg_read(UC_ARM64_REG_X0);x1=uc.reg_read(UC_ARM64_REG_X1)
        calls.append((name,x0,x1))
        if name=='new':
            assert x0==24;uc.reg_write(UC_ARM64_REG_X0,0x70000300)
        elif name=='isvisible':
            assert x0==0x70000200;uc.reg_write(UC_ARM64_REG_X0,applied)
        elif name=='visible':assert x0==0x70000200 and x1==desired
        elif name=='schedule':
            assert x0==INTERVAL and x1==0 and uc.reg_read(UC_ARM64_REG_X2)==0
            slot=uc.reg_read(UC_ARM64_REG_X3)
            assert bytes(uc.mem_read(slot,24))==struct.pack('<QQQ',1,base+CAVE,0)
        elif name=='quit':assert x0==0
        uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_LR))
    u.mem_protect(base+CAVE//4096*4096,4096,5) # Actual callback page is RX.
    u.hook_add(UC_HOOK_CODE,stub)
    u.reg_write(UC_ARM64_REG_SP,0x7000f000);u.reg_write(UC_ARM64_REG_LR,base+0x100)
    u.reg_write(UC_ARM64_REG_X0,mode);u.reg_write(UC_ARM64_REG_X1,0x70000300)
    for reg in (UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22):u.reg_write(reg,0x1234)
    u.emu_start(base+HOOK,base+0x100,count=600)
    assert u.reg_read(UC_ARM64_REG_PC)==base+0x100
    assert u.reg_read(UC_ARM64_REG_SP)==0x7000f000
    for reg in (UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22):assert u.reg_read(reg)==0x1234
    kinds=[c[0] for c in calls]
    if mode==0:assert kinds==['delete']
    elif mode==2:assert not kinds
    elif desired==2:assert kinds==['quit']
    else:
        assert kinds==(['isvisible'] if windows==1 else [])+(['visible'] if windows==1 and desired!=applied else [])+['new','schedule']
        assert bytes(u.mem_read(box,4))==bytes([desired,applied,0,0])
    cases.append({'operation':mode,'desired':desired,'applied':applied,'windows':windows,'calls':kinds})
for name,data in [('resident-code.bin',blob),('resident-hook.bin',branch)]: (OUT/name).write_bytes(data)
meta={'firmware':'X2D 100C 4.2.0','guiSha256':SHA,'cave':CAVE,'hook':HOOK,'mailbox':CAVE+mailbox,'length':len(blob),'originalCaveHash':hashlib.sha256(b.read(CAVE,len(blob))).hexdigest(),'originalHookHash':hashlib.sha256(b.read(HOOK,4)).hexdigest(),'codeHash':hashlib.sha256(blob).hexdigest(),'hookHash':hashlib.sha256(branch).hexdigest(),'offlineCases':cases,'deviceValidated':False}
meta['intervalMs']=INTERVAL
(OUT/'resident-page-candidate.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
print(json.dumps({'result':'pass','cases':len(cases),'bytes':len(blob),'mailboxOffset':mailbox,'deviceValidated':False}))
