"""构建常驻输入候选，仅离线，库来源绑定原厂 4.2.0。"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
ROOT = D.parents[2]
OUT = D / 'native-input-candidate'
OUT.mkdir(exist_ok=True)
sys.path[:0] = [str(ROOT/'.research-cache/python'), str(ROOT/'.research-cache/x1d-1.25.0/python'), str(ROOT/'x2d/tools')]
from firmware_image import system_file
from elftools.elf.elffile import ELFFile
deps = []
exports = set()
for name in ('libc.so', 'libdbus.so'):
    raw = system_file('/lib64/' + name)
    (OUT / name).write_bytes(raw)
    deps.append({'path': '/system/lib64/'+name, 'sha256': hashlib.sha256(raw).hexdigest()})
    elf = ELFFile(io.BytesIO(raw))
    exports.update(s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx'] != 'SHN_UNDEF')
env = os.environ.copy()
env['ZIG_LOCAL_CACHE_DIR'] = str(D/'.zig-cache')
env['ZIG_GLOBAL_CACHE_DIR'] = str(D/'.zig-global')
zig = ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
target = OUT/'libx2d_menu_input.so'
subprocess.run([str(zig),'cc','-g0','-target','aarch64-linux-gnu','-DRESIDENT_INTERVAL_MS=5','-c',str(D/'resident_page.S'),'-o',str(OUT/'resident_page.o')],env=env,check=True)
subprocess.run([sys.executable,'-B',str(D/'build_resident_page.py'),'--fast'],env=env,check=True)
subprocess.run([str(zig), 'cc', '-target', 'aarch64-linux-gnu', '-O2', '-fPIC', '-shared', '-nostdlib',
                '-fno-stack-protector', '-Wl,--no-undefined', '-Wl,-z,noexecstack', '-Wl,-soname,libx2d_menu_input.so',
                str(D/'native_menu_input.c'), str(OUT/'libdbus.so'), str(OUT/'libc.so'), '-o', str(target)], env=env, check=True)
raw = target.read_bytes()
elf = ELFFile(io.BytesIO(raw))
assert elf['e_machine'] == 'EM_AARCH64'
assert not any((s['p_flags'] & 3) == 3 for s in elf.iter_segments())
imports = {s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name and s['st_shndx'] == 'SHN_UNDEF'}
assert imports <= exports, imports - exports
needed = [t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag == 'DT_NEEDED']
assert set(needed) == {'libc.so','libdbus.so'}, needed
manifest = {'sourceFirmware': 'X2D 100C 4.2.0', 'dependencies': deps,
            'sha256': hashlib.sha256(raw).hexdigest(), 'imports': sorted(imports), 'needed': needed,
            'deviceValidated': False, 'installed': False,
            'limitations': ['5ms Qt visibility callback not yet tested on hardware', 'boot script still initializes addresses',
                            'persistent bus connection and input permissions require dedicated inspect test']}
(OUT/'build.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'compiled': True,'bytes': len(raw),'imports': len(imports),'deviceValidated': False}))
