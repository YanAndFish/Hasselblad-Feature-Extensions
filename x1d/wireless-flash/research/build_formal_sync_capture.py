"""编译机械/电子共存的固定 X1D 1.25.0 采集程序；没有设备访问。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / 'build/formal-sync-capture'
HOOKS = {
    0x21409c: (0xeb0091df, 'formal_sync_clear_hook', True),
    0x21410c: (0xeb0091c3, 'formal_sync_start_hook', True),
    0x213e60: (0xeb0092cd, 'formal_sync_status_hook', True),
    0x213ef8: (0xeb0092a7, 'formal_sync_status_hook', True),
    0x2143e4: (0xeb00916c, 'formal_sync_finish_hook', True),
    0x1c4380: (0xe3013690, 'formal_sync_observe_hook', False),
    0x1c4458: (0xe1a03000, 'formal_sync_progress_hook', False),
    0x1c44f4: (0xe3a00001, 'formal_sync_stop_hook', False),
}


def build(target=False):
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError('workspace mismatch')
    OUT.mkdir(exist_ok=True)
    env = dict(os.environ)
    for key, name in (('ZIG_GLOBAL_CACHE_DIR', 'global-cache'), ('ZIG_LOCAL_CACHE_DIR', 'local-cache'),
                      ('TEMP', 'tmp'), ('TMP', 'tmp')):
        p = OUT / name
        p.mkdir(exist_ok=True)
        env[key] = str(p)
    name, base = ('target', 0x2b2880) if target else ('simulation', 0x1000000)
    layout = OUT / (name + '.ld')
    layout.write_text('''ENTRY(formal_sync_clear_hook)
SECTIONS {
 . = %s;
 .text : { KEEP(*(.text.formal_sync_clear_hook)) KEEP(*(.text.formal_sync_*_hook)) *(.text*) }
 .data : ALIGN(4) { *(.data.formal_sync_record) }
 ASSERT(SIZEOF(.data) == 364, "wrong formal record size")
 %s
 /DISCARD/ : { *(.comment) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
}
''' % (hex(base), 'ASSERT(ADDR(.data) + SIZEOF(.data) <= 0x2b3f40, "reserved helper overlap")' if target else ''), encoding='ascii')
    compiler = ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    sources = [HERE / 'native/formal_sync_capture.c', HERE / 'native/formal_sync_hooks.S']
    output = OUT / (name + '.elf')
    command = [str(compiler), 'cc', '-target', 'arm-freestanding-eabi', '-mcpu=cortex_a9',
               '-mfloat-abi=soft', '-marm', '-Os', '-g', '-fno-lto', '-ffunction-sections',
               '-fdata-sections', '-ffreestanding', '-fno-stack-protector', '-fno-unwind-tables',
               '-fno-asynchronous-unwind-tables', '-fPIC', '-Wl,--no-undefined', '-nostdlib',
               '-Wl,--build-id=none', '-Wall', '-Wextra', '-Werror', '-Wl,-T,' + str(layout),
               *map(str, sources), '-o', str(output)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr)
    sys.path.insert(0, str(ROOT / 'x1d/tools'))
    from binary import ArmElf
    elf = ArmElf(output.read_bytes())
    sections = [elf.elf.get_section_by_name(n) for n in ('.text', '.data')]
    if any(s is None for s in sections) or sections[0]['sh_addr'] != base or sections[1]['sh_size'] != 364:
        raise RuntimeError('layout mismatch')
    if any(s['sh_type'] in ('SHT_REL', 'SHT_RELA') and s['sh_size'] for s in elf.sections):
        raise RuntimeError('runtime relocation')
    end = sections[1]['sh_addr'] + sections[1]['sh_size']
    payload = bytearray(end - base)
    for section in sections:
        offset = section['sh_addr'] - base
        payload[offset:offset + section['sh_size']] = section.data()
    (OUT / (name + '.bin')).write_bytes(payload)
    symbols = {s.name: s['st_value'] for section in elf.sections if section['sh_type'] == 'SHT_SYMTAB'
               for s in section.iter_symbols()}
    report = {'status': '离线构建，尚未装载', 'command': command,
              'elf_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'payload_sha256': hashlib.sha256(payload).hexdigest(), 'payload_bytes': len(payload),
              'base': base, 'end_exclusive': end, 'record_address': sections[1]['sh_addr'],
              'record_size': 364, 'hook_entries': {n: symbols[n] for _, n, _ in HOOKS.values()},
              'hooks': [{'address': a, 'original': v, 'target': symbols[n], 'link': link} for a, (v, n, link) in HOOKS.items()],
              'sources': {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sources + [HERE / 'native/mechanical_sync_wire.h', HERE / 'native/farm_sync_wire.h', Path(__file__)]},
              'hardware_requests': 0, 'installed': False, 'physical_timing_measured': False}
    (OUT / (name + '-build.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    for target in (False, True):
        report = build(target)
        print(json.dumps({k: report[k] for k in ('status', 'base', 'end_exclusive', 'payload_bytes', 'payload_sha256')}, ensure_ascii=False))
