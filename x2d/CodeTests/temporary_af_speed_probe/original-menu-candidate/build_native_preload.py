"""构建原厂菜单独立启动模块；仅离线，不安装、不重启。"""
import hashlib
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
D=Path(__file__).resolve().parent
ROOT=D.parents[3]
sys.path.insert(0,str(D.parent))
from inspect_menu_resources import load_gui, GUI_SHA
from firmware_image import system_file
from elftools.elf.elffile import ELFFile

O=D/'native-package'
O.mkdir(exist_ok=True)
b=load_gui()
symbol=next(s for s in b.symbols if s.name.endswith('32_app_qml_mainmenu_MainScreen_qml7qmlDataE'))
stock=b.read(symbol['st_value'],symbol['st_size'])
(O/'stock-unit.bin').write_bytes(stock)
clone=(D/'main-screen-bootstrap-device.bin').read_bytes()
assert 15084 < len(clone) < 20000
(O/'extended-unit.bin').write_bytes(clone)
assembly='.section .rodata\n.balign 8\n'
for label,file in [('stock_unit','stock-unit.bin'),('extended_unit','extended-unit.bin'),
                   ('control_stock','control-stock.bin'),('control_afc','control-afc.bin'),
                   ('popover_stock','popover-stock.bin'),('popover_afc','popover-afc.bin')]:
    assembly+=f'.global {label}, {label}_end\n{label}:\n.incbin "{(O/file).as_posix()}"\n{label}_end:\n.balign 8\n'
(O/'units.S').write_text(assembly)
exports=set()
deps=[]
for name in ('libc.so','libdl.so'):
    raw=system_file('/lib64/'+name)
    (O/name).write_bytes(raw)
    elf=ELFFile(io.BytesIO(raw))
    exports.update(s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF')
    deps.append(dict(name=name,sha256=hashlib.sha256(raw).hexdigest()))
env=os.environ.copy()
env['ZIG_LOCAL_CACHE_DIR']=str(D.parent/'.zig-cache')
env['ZIG_GLOBAL_CACHE_DIR']=str(D.parent/'.zig-global')
zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
target=O/'libx2d_native_menu.so'
subprocess.run([str(zig),'cc','-target','aarch64-linux-gnu','-O2','-g0','-fPIC','-shared','-nostdlib',
               '-DEXTENDED_UNIT_SIZE='+str(len(clone)),
               '-fno-stack-protector','-Wl,--strip-all','-Wl,--no-undefined','-Wl,-z,noexecstack',
               '-Wl,-soname,libx2d_native_menu.so',str(D/'native_menu_preload.c'),str(O/'units.S'),
               str(O/'libc.so'),str(O/'libdl.so'),'-o',str(target)],env=env,check=True)
raw=target.read_bytes();elf=ELFFile(io.BytesIO(raw))
assert elf['e_machine']=='EM_AARCH64'
assert not any((s['p_flags']&3)==3 for s in elf.iter_segments())
imports={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF'}
assert imports<=exports, imports-exports
files=[]
names={'Bootstrap':'X2dNativeMenuBootstrap','FlashMenuModel':'X2dNativeMenuModel',
       'FlashMenuRoute':'X2dNativeMenuRoute','ResidentFlashHost':'X2dNativeMenuHost'}
sources=[D/(name+'.qml') for name in names]
for source in sorted((D.parent/'menu-candidate/flash-ui').glob('*.qml')):
    names[source.stem]='X2d'+source.stem
    sources.append(source)
paths=[target]
for source in sources:
    text=source.read_text(encoding='utf-8').replace('../menu-candidate/flash-ui','.')
    text=re.sub(r'\b('+'|'.join(names)+r')\b',lambda m:names[m[0]],text)
    path=O/(names[source.stem]+'.qml')
    path.write_text(text,encoding='utf-8',newline='\n')
    paths.append(path)
for path in paths:
    location='/system/lib64/' if path==target else '/system/etc/'
    files.append(dict(source=path.name,target=location+path.name,bytes=path.stat().st_size,
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
report=dict(guiSha256=GUI_SHA,files=files,dependencies=deps,imports=sorted(imports),
            deployed=False,deviceValidated=False,bootConfigurationWritten=False,
            guard='exact three units/cache pointers; opt-in; disable-file; once per boot; rollback all four writes',
            afcFocusPopover=True, flashPressedHighlightCorrected=True)
(O/'package.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(compiled=True,files=len(files),bytes=len(raw),deviceValidated=False)))
