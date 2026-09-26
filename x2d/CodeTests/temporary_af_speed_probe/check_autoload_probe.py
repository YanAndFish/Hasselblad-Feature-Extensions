"""离线执行诊断模块 ARM64 构造函数；模拟 libc，不访问相机。"""
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

elf = ELFFile(io.BytesIO((D / 'libx2d_preview_probe.so').read_bytes()))
assert elf['e_machine'] == 'EM_AARCH64' and elf['e_type'] == 'ET_DYN'
assert all(not (p['p_flags'] & 1 and p['p_flags'] & 2) for p in elf.iter_segments())
dyn = elf.get_section_by_name('.dynamic')
assert not any(t.entry.d_tag == 'DT_TEXTREL' for t in dyn.iter_tags())
assert [t.needed for t in dyn.iter_tags() if t.entry.d_tag == 'DT_NEEDED'] == ['libc.so']
imports = {s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s.name and s['st_shndx'] == 'SHN_UNDEF'}
assert imports == {'getenv', 'open', 'read', 'close', '_exit', 'getuid', 'getauxval', 'write'}
libc = ELFFile(io.BytesIO(system_file('/lib64/libc.so')))
exports = {s.name for s in libc.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx'] != 'SHN_UNDEF'}
assert imports <= exports

good = b'/system/bin/camera-test\0--version\0'
cases = [
    ('opt_in_absent', False, good, False, False, False, None),
    ('main_gui_untouched', True, b'/system/bin/camera-gui\0--fullscreen\0', False, False, False, None),
    ('ordinary_test_service_untouched', True, b'/system/bin/camera-test\0', False, False, False, None),
    ('wrong_program_untouched', True, good.replace(b'camera-test', b'camera-xxxx'), False, False, False, None),
    ('truncated_cmdline', True, good[:-1], False, False, False, None),
    ('selected_success', True, good, False, False, False, 0),
    ('existing_status_refused', True, good, True, False, False, 21),
    ('context_read_failure', True, good, False, True, False, 22),
    ('short_write_failure', True, good, False, False, True, 22),
]
results = []
for name, opt, cmd, output_fail, context_fail, short_write, expected in cases:
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    base, stubs, scratch = 0x40000000, 0x60000000, 0x70000000
    u.mem_map(base, 0x40000)
    u.mem_map(stubs, 0x10000)
    u.mem_map(scratch, 0x20000)
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
    # Preserve non-writable code in the simulation.
    for p in elf.iter_segments():
        if p['p_type'] == 'PT_LOAD' and p['p_flags'] & 1:
            lo = p['p_vaddr'] & ~4095
            hi = (p['p_vaddr'] + p['p_memsz'] + 4095) & ~4095
            u.mem_protect(base + lo, hi - lo, 5)
    u.mem_write(scratch, b'1\0')
    events, output, exit_codes = [], bytearray(), []
    def cstr(addr):
        result = bytearray()
        for i in range(4096):
            c = bytes(u.mem_read(addr + i, 1))
            if c == b'\0': return result.decode()
            result.extend(c)
        raise AssertionError('unterminated string')
    def call(uc, address, size, opaque):
        fn = names.get(address)
        if not fn: return
        a, b, c = [uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        ret = 0
        if fn == 'getenv':
            assert cstr(a) == 'X2D_AUTOLOAD_PROBE'; ret = scratch if opt else 0
        elif fn == 'open':
            path = cstr(a); events.append(path)
            if path == '/proc/self/cmdline': assert b == 0; ret = 3
            elif path == '/proc/self/attr/current': assert b == 0; ret = -1 if context_fail else 4
            else:
                assert path == '/tmp/x2d-autoload-probe/status' and b == 0x200c1 and c == 0o600
                ret = -1 if output_fail else 5
        elif fn == 'read':
            data = cmd if a == 3 else b'u:r:hbl_camera_service:s0\n'
            assert a in (3, 4); data = data[:c]; uc.mem_write(b, data); ret = len(data)
        elif fn == 'write':
            assert a == 5
            ret = c - 1 if short_write else c
            output.extend(bytes(uc.mem_read(b, ret)))
        elif fn == 'close': assert a in (3, 4, 5)
        elif fn == 'getuid': ret = 0
        elif fn == 'getauxval': assert a == 23; ret = 0
        elif fn == '_exit': exit_codes.append(a); uc.emu_stop(); return
        uc.reg_write(UC_ARM64_REG_X0, ret & ((1 << 64) - 1))
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE, call)
    u.reg_write(UC_ARM64_REG_SP, scratch + 0x1f000)
    u.reg_write(UC_ARM64_REG_LR, stubs)
    init = elf.get_section_by_name('.init_array')['sh_addr']
    start = struct.unpack('<Q', bytes(u.mem_read(base + init, 8)))[0]
    u.emu_start(start, stubs, count=50000)
    assert exit_codes == ([] if expected is None else [expected]), (name, exit_codes)
    if expected is None: assert '/tmp/x2d-autoload-probe/status' not in events
    if expected == 0: assert output == b'module_loaded=1\nuid=root\nsecure=0\ndomain=u:r:hbl_camera_service:s0\n\n'
    results.append(name)
print(json.dumps({'result': 'pass', 'cases': results, 'deviceAccesses': 0,
                  'limitation': '模拟 libc 与构造函数；未验证相机动态装载、init 服务、重挂载或开机行为'}, ensure_ascii=False))
