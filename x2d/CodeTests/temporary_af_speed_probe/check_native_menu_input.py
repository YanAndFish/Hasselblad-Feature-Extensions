"""ARM64 候选的纯状态决策和构造函数拒绝路径；不访问相机。"""
import io
import json
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
ROOT = D.parents[2]
sys.path[:0] = [str(ROOT/'.research-cache/python'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_SP,UC_ARM64_REG_LR,UC_ARM64_REG_PC
OUT = D/'native-input-candidate'
elf = ELFFile(io.BytesIO((OUT/'libx2d_menu_input.so').read_bytes()))
symbols = {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
BASE,STUB,DATA,END = 0x40000000,0x60000000,0x70000000,0x7001f000

def machine():
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    u.mem_map(BASE,0x100000);u.mem_map(STUB,0x10000);u.mem_map(DATA,0x20000)
    for seg in elf.iter_segments():
        if seg['p_type']=='PT_LOAD':u.mem_write(BASE+seg['p_vaddr'],seg.data())
    names={}
    for sec in elf.iter_sections():
        if sec['sh_type']!='SHT_RELA':continue
        syms=elf.get_section(sec['sh_link'])
        for r in sec.iter_relocations():
            if r['r_info_type']==1027:value=BASE+r['r_addend']
            elif r['r_info_type'] in (1025,1026):
                sym=syms.get_symbol(r['r_info_sym'])
                if sym['st_shndx']!='SHN_UNDEF':value=BASE+sym['st_value']
                else:
                    value=STUB+0x100+len(names)*16;names[value]=sym.name
            else:raise AssertionError(r['r_info_type'])
            u.mem_write(BASE+r['r_offset'],struct.pack('<Q',value))
    u.reg_write(UC_ARM64_REG_SP,DATA+0x18000);u.reg_write(UC_ARM64_REG_LR,END)
    return u,names

decisions=[]
for shown in (0,1):
    for lv in (-1,0,1,2,3,4,9):
        for exp in (-1,0,2,512):
            u,names=machine()
            for reg,value in zip((UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2),(shown,lv,exp)):u.reg_write(reg,value&0xffffffff)
            u.emu_start(BASE+symbols['menu_decide'],END,count=500)
            result=u.reg_read(UC_ARM64_REG_X0)&0xffffffff
            expected=2 if shown else (0 if exp not in (0,512) else (1 if lv==0 else (3 if lv==1 else 0)))
            assert result==expected,(shown,lv,exp,result,expected)
            decisions.append([shown,lv,exp,result])

good=b'/system/bin/camera-test\0--version\0'
cases=[('disabled',None),('wrong_host',81),('extra_args',81),('read_failed',81),('unset_failed',82),('existing_log',83),('missing_config',84)]
for case,expected in cases:
    u,names=machine();u.mem_write(DATA,b'inspect\0');state={'exit':None,'calls':[]}
    def string(addr):
        b=bytearray()
        for i in range(4096):
            c=bytes(u.mem_read(addr+i,1))
            if c==b'\0':return b.decode()
            b.extend(c)
        raise AssertionError('unterminated')
    def hook(uc,address,size,opaque):
        name=names.get(address)
        if not name:return
        state['calls'].append(name)
        a,b,c=[uc.reg_read(x) for x in (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2)]
        ret=0
        if name=='getenv':assert string(a)=='X2D_MENU_INPUT_MODE';ret=0 if case=='disabled' else DATA
        elif name=='open':
            path=string(a)
            if path=='/proc/self/cmdline':ret=3
            elif path=='/tmp/x2d-preview/native-inspect.log':ret=-1 if case=='existing_log' else 4
            elif path=='/tmp/x2d-preview/native-state':ret=-1
            else:raise AssertionError(path)
        elif name=='read':
            assert a==3
            raw=(b'/system/bin/camera-gui\0' if case=='wrong_host' else good+b'extra\0' if case=='extra_args' else good)
            if case=='read_failed':ret=-1
            else:uc.mem_write(b,raw);ret=len(raw)
        elif name=='close':pass
        elif name=='unsetenv':assert string(a) in ('LD_PRELOAD','X2D_MENU_INPUT_MODE');ret=-1 if case=='unset_failed' else 0
        elif name=='clock_gettime':uc.mem_write(b,struct.pack('<qq',1,0))
        elif name=='snprintf':ret=0 # error logging only; no functional decisions use it in these cases
        elif name=='_exit':state['exit']=a;uc.emu_stop();return
        else:raise AssertionError('Unexpected operation on rejection path: '+name)
        uc.reg_write(UC_ARM64_REG_X0,ret&((1<<64)-1));uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    u.emu_start(BASE+symbols['start_native_input'],END,count=20000)
    assert state['exit']==expected,(case,state)
    assert not any(n.startswith('dbus_') or n=='pwrite' for n in state['calls'])
(OUT/'offline-validation.json').write_text(json.dumps({'decisionCases':len(decisions),'constructorRejectionCases':len(cases),'deviceAccesses':0,'hardwareLatencyMeasured':False},indent=2)+'\n')
print('NATIVE_OFFLINE_OK decisions=%d rejection_cases=%d'%(len(decisions),len(cases)))
