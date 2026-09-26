"""运行 ARM64 构造函数，覆盖启动栅栏的宿主匹配、超时和异常。"""
import io
import json
import struct
import sys
from pathlib import Path
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
ROOT = D.parents[2]
sys.path[:0] = [str(ROOT / '.research-cache/python'), str(ROOT / '.research-cache/x1d-1.25.0/python'), str(ROOT / 'x2d/tools')]
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC
from firmware_image import system_file

elf = ELFFile(io.BytesIO((D / 'libx2d_menu_gate.so').read_bytes()))
assert not any(p['p_flags'] & 1 and p['p_flags'] & 2 for p in elf.iter_segments())
imports = {s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name and s['st_shndx'] == 'SHN_UNDEF'}
assert imports == {'getenv', 'unsetenv', 'open', 'read', 'write', 'close', 'usleep', '_exit'}
libc = ELFFile(io.BytesIO(system_file('/lib64/libc.so')))
assert imports <= {s.name for s in libc.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx'] != 'SHN_UNDEF'}
assert [t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag == 'DT_NEEDED'] == ['libc.so']
good = b'\0'.join(s.encode() for s in ['/system/bin/camera-gui', '-platform', 'wayland-egl', '--fullscreen', '--bus', 'none', '--imagetest', '-u', 'file:/system/etc/x2d-preview-page.png', '-o', '2147483647', '-e', '2147483646', '--timeout', '5']) + b'\0'
cases = [('disabled', None), ('main_gui', 81), ('extra_argument', 81), ('truncated', 81), ('cmd_failed', 80),
         ('unset_failed', 82), ('ready_exists', 83), ('short_write', 84), ('bad_release', 85),
         ('sleep_failed', 86), ('timeout', 87), ('delayed_release', None)]
results = []
for case, expected in cases:
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    base, stubs, scratch = 0x40000000, 0x60000000, 0x70000000
    u.mem_map(base, 0x40000); u.mem_map(stubs, 0x10000); u.mem_map(scratch, 0x20000)
    for p in elf.iter_segments():
        if p['p_type'] == 'PT_LOAD': u.mem_write(base + p['p_vaddr'], p.data())
    names = {}
    for sec in elf.iter_sections():
        if sec['sh_type'] != 'SHT_RELA': continue
        symbols = elf.get_section(sec['sh_link'])
        for r in sec.iter_relocations():
            if r['r_info_type'] == 1027: value = base + r['r_addend']
            else:
                assert r['r_info_type'] == 1026
                value = stubs + 0x100 + len(names) * 16
                names[value] = symbols.get_symbol(r['r_info_sym']).name
            u.mem_write(base + r['r_offset'], struct.pack('<Q', value))
    u.mem_write(scratch, b'1\0')
    state = {'slept': 0, 'release': False, 'ready': False, 'exit': None, 'cleared': []}
    def text(addr):
        out = bytearray()
        for i in range(2048):
            c = bytes(u.mem_read(addr + i, 1))
            if c == b'\0': return out.decode()
            out.extend(c)
        raise AssertionError('unterminated')
    def call(uc, address, size, opaque):
        fn = names.get(address)
        if not fn: return
        a, b, c = [uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        ret = 0
        if fn == 'getenv':
            assert text(a) == 'X2D_MENU_CHILD'; ret = 0 if case == 'disabled' else scratch
        elif fn == 'unsetenv':
            state['cleared'].append(text(a)); ret = -1 if case == 'unset_failed' else 0
        elif fn == 'open':
            path = text(a)
            if path == '/proc/self/cmdline':
                assert b == 0; ret = -1 if case == 'cmd_failed' else 3
            elif path == '/tmp/x2d-preview/menu-ready':
                assert b == 0x200c1 and c == 0o600
                assert state['cleared'] == ['LD_PRELOAD', 'X2D_MENU_CHILD']
                ret = -1 if case == 'ready_exists' else 4
            elif path == '/tmp/x2d-preview/menu-go':
                assert b == 0x20000 and state['ready']
                ret = 5 if case == 'bad_release' or (case == 'delayed_release' and state['slept'] == 3) else -1
            else: raise AssertionError(path)
        elif fn == 'read':
            if a == 3:
                data = good
                if case == 'main_gui': data = b'/system/bin/camera-gui\0-platform\0wayland-egl\0--fullscreen\0'
                if case == 'truncated': data = good[:-1]
                if case == 'extra_argument': data = good + b'x\0'
            else:
                assert a == 5; data = b'0' if case == 'bad_release' else b'1'; state['release'] = data == b'1'
            data = data[:c]; uc.mem_write(b, data); ret = len(data)
        elif fn == 'write':
            assert a == 4 and bytes(uc.mem_read(b, c)) == b'READY\n'
            state['ready'] = True; ret = 1 if case == 'short_write' else c
        elif fn == 'close': assert a in (3, 4, 5)
        elif fn == 'usleep':
            assert a == 20000; state['slept'] += 1; ret = -1 if case == 'sleep_failed' else 0
        elif fn == '_exit': state['exit'] = a; uc.emu_stop(); return
        uc.reg_write(UC_ARM64_REG_X0, ret & ((1 << 64) - 1))
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE, call)
    u.reg_write(UC_ARM64_REG_SP, scratch + 0x1f000)
    u.reg_write(UC_ARM64_REG_LR, stubs)
    start = struct.unpack('<Q', bytes(u.mem_read(base + elf.get_section_by_name('.init_array')['sh_addr'], 8)))[0]
    u.emu_start(start, stubs, count=100000)
    assert state['exit'] == expected, (case, state)
    if case == 'timeout': assert state['slept'] == 750
    if case == 'delayed_release': assert state['release'] and state['slept'] == 3
    if expected is None: assert u.reg_read(UC_ARM64_REG_PC) == stubs
    results.append(case)
print(json.dumps(dict(result='pass', deviceAccesses=0, cases=results)))
