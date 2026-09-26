"""离线执行 ARM64 构造器，验证三份缓存挂接与四处写入逐项失败恢复。"""
import io
import json
import struct
import sys
from pathlib import Path
sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
ROOT=D.parents[3]
sys.path[:0]=[str(ROOT/'.research-cache/python'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC

O=D/'native-package'
elf=ELFFile(io.BytesIO((O/'libx2d_native_menu.so').read_bytes()))
cases=['success','not_enabled','disabled','retry','wrong_control','wrong_popover','bad_gate','open_fail']+[f'short_{i}' for i in range(1,5)]
results=[]
for case in cases:
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    lib,app,stubs,scratch=0x40000000,0x10000000,0x60000000,0x70000000
    u.mem_map(lib,0x100000);u.mem_map(app,0x3000000);u.mem_map(stubs,0x10000);u.mem_map(scratch,0x20000)
    for p in elf.iter_segments():
        if p['p_type']=='PT_LOAD': u.mem_write(lib+p['p_vaddr'],p.data())
    names={}
    for sec in elf.iter_sections():
        if sec['sh_type']!='SHT_RELA': continue
        symbols=elf.get_section(sec['sh_link'])
        for r in sec.iter_relocations():
            if r['r_info_type']==1027: value=lib+r['r_addend']
            else:
                symbol=symbols.get_symbol(r['r_info_sym'])
                if symbol['st_shndx']!='SHN_UNDEF': value=lib+symbol['st_value']+r['r_addend']
                else:
                    assert r['r_info_type'] in (1025,1026)
                    value=stubs+0x100+len(names)*16;names[value]=symbol.name
            u.mem_write(lib+r['r_offset'],struct.pack('<Q',value))
    entries=[(0x20acc78,0x17b67f0,0x216d650,'stock-unit.bin'),
             (0x20ac690,0x16c6300,0x215cc90,'control-stock.bin'),
             (0x20ad2c0,0x1876ea0,0x217aec0,'popover-stock.bin')]
    for cache,unit,aot,file in entries:
        u.mem_write(app+unit,(O/file).read_bytes())
        u.mem_write(app+cache,struct.pack('<3Q',app+unit,app+aot,0))
    if case=='wrong_control':u.mem_write(app+0x16c6300+500,b'\xff')
    if case=='wrong_popover':u.mem_write(app+0x1876ea0+500,b'\xff')
    u.mem_write(app+0x18a2a64,struct.pack('<I',7 if case=='bad_gate' else 0))
    fields=[(app+c,8) for c,_,_,_ in entries]+[(app+0x18a2a64,4)]
    before=[bytes(u.mem_read(a,n)) for a,n in fields]
    u.mem_write(scratch,b'1\0')
    state=dict(position=0,writes=0,status='',attempt=False)
    def cstr(address):
        out=bytearray()
        for i in range(4096):
            ch=bytes(u.mem_read(address+i,1))
            if ch==b'\0':return out.decode()
            out.extend(ch)
        raise AssertionError('unterminated')
    def call(uc,address,size,opaque):
        fn=names.get(address)
        if not fn:return
        a,b,c=[uc.reg_read(r) for r in (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2)]
        ret=0
        if fn=='getenv':ret=0 if case=='not_enabled' else scratch
        elif fn=='readlink':
            assert cstr(a)=='/proc/self/exe'
            data=b'/system/bin/camera-gui';uc.mem_write(b,data);ret=len(data)
        elif fn=='strcmp':ret=0 if cstr(a)==cstr(b) else 1
        elif fn=='memcmp':ret=0 if bytes(uc.mem_read(a,c))==bytes(uc.mem_read(b,c)) else 1
        elif fn=='dl_iterate_phdr':uc.mem_write(b,struct.pack('<Q',app));ret=1
        elif fn=='open':
            path=cstr(a)
            if path=='/blackbox/x2d-native-menu.disable':ret=3 if case=='disabled' else -1
            elif path=='/tmp/x2d-native-menu-attempt':
                assert b==193
                ret=-1 if case=='retry' else 4;state['attempt']=ret==4
            elif path=='/proc/self/mem':ret=-1 if case=='open_fail' else 5
            elif path=='/tmp/x2d-native-menu-preload.status':ret=6
            else:raise AssertionError(path)
        elif fn=='close':pass
        elif fn=='lseek':assert a==5 and c==0;state['position']=b;ret=b
        elif fn=='write':
            if a==6:state['status']+=bytes(uc.mem_read(b,c)).decode();ret=c
            else:
                assert a==5
                state['writes']+=1
                partial=case==f'short_{state["writes"]}'
                ret=c-1 if partial else c
                uc.mem_write(state['position'],bytes(uc.mem_read(b,ret)))
        else:raise AssertionError(fn)
        uc.reg_write(UC_ARM64_REG_X0,ret&((1<<64)-1));uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE,call)
    u.reg_write(UC_ARM64_REG_SP,scratch+0x1f000);u.reg_write(UC_ARM64_REG_LR,stubs)
    init=elf.get_section_by_name('.init_array')['sh_addr']
    start=struct.unpack('<Q',bytes(u.mem_read(lib+init,8)))[0]
    u.emu_start(start,stubs,count=2000000)
    assert u.reg_read(UC_ARM64_REG_PC)==stubs,(case,hex(u.reg_read(UC_ARM64_REG_PC)),state)
    after=[bytes(u.mem_read(a,n)) for a,n in fields]
    if case=='success':
        assert all(x!=y for x,y in zip(before,after))
        for value,file in zip(after[:3],['extended-unit.bin','control-afc.bin','popover-afc.bin']):
            ptr=struct.unpack('<Q',value)[0];expected=(O/file).read_bytes()
            assert bytes(u.mem_read(ptr,len(expected)))==expected
        assert after[3]==b'\x01\0\0\0' and state['status']=='MENU_AND_AFC_POINTERS_READY\n'
    else:
        assert after==before,(case,state)
        if case.startswith('short_'):assert state['status']=='WRITE_FAILED_RESTORED\n'
    results.append(dict(case=case,status=state['status'].strip(),memoryWrites=state['writes']))
report=dict(result='PASS',cases=results,cameraAccesses=0,limitation='ARM64 constructor with simulated libc and process memory; not device GUI/AF validation')
(D/'combined-preload-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
