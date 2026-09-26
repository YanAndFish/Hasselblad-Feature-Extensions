"""从已绑定的 AF release 来源生成机内重定位表；只做离线构建。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'x1d/af-experiment/camera-settings-r1/delivery-r7'
OUT = HERE / 'build/boot-data'

def word_list(blob):
    return list(struct.unpack('<' + 'I' * (len(blob) // 4), blob))

def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('current workspace required')
    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('boot_af_candidate', SOURCE / 'candidate.py')
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    bindings = dict(candidate.build.__globals__, DELIVERY=OUT)
    source = candidate.source.replace("out=HERE/'build'/profile/f'{base:08x}'", "out=DELIVERY/'build'/profile/f'{base:08x}'")
    exec(compile(source, __file__, 'exec'), bindings)
    candidate.build = bindings['build']
    bases = (0x800000, 0x2bace0, 0x39cec0, 0x6b2c80)
    builds = [candidate.build(base, 'release') for base in bases]
    manifests = [m for m, _ in builds]
    blobs = [(p / 'candidate.bin').read_bytes() for _, p in builds]
    words = [word_list(blob) for blob in blobs]
    original = manifests[0]
    reviewed = json.loads((SOURCE / 'reviewed-profile-sources.json').read_text())['release']
    if original['source_sha256'] != reviewed:
        raise RuntimeError('reviewed release source identity')
    relocations = []
    for obj_path in (builds[0][1] / 'cache').rglob('*.o'):
        if obj_path.name.startswith('lib'):
            continue
        obj = bindings['ArmElf'](obj_path.read_bytes())
        for section in obj.sections:
            if section['sh_type'] != 'SHT_REL':
                continue
            target = obj.sections[section['sh_info']]
            if not target['sh_flags'] & 2 or target.name.startswith('.ARM'):
                continue
            anchors = {(original['symbols'][s.name] & ~1) - (s['st_value'] & ~1)
                for s in obj.symbols if s['st_shndx'] == section['sh_info']
                and s.name and not s.name.startswith('$') and s.name in original['symbols']}
            if len(anchors) != 1:
                raise RuntimeError('ambiguous object placement: ' + obj_path.name + target.name)
            section_base = anchors.pop()
            symbols = obj.sections[section['sh_link']]
            for relocation in section.iter_relocations():
                kind = relocation['r_info_type']
                if kind not in (2, 47, 48):
                    continue
                symbol = symbols.get_symbol(relocation['r_info_sym'])
                if symbol.name not in original['symbols']:
                    raise RuntimeError('unresolved absolute relocation')
                value = original['symbols'][symbol.name]
                if not bases[0] <= (value & ~1) < original['end']:
                    continue
                at = relocation['r_offset']
                offset = section_base + at - bases[0]
                if kind == 2:
                    addend = struct.unpack_from('<I', target.data(), at)[0]
                else:
                    hi, lo = struct.unpack_from('<HH', target.data(), at)
                    addend = ((hi & 15) << 12) | ((hi & 0x400) << 1) | ((lo & 0x7000) >> 4) | (lo & 255)
                if addend:
                    raise RuntimeError('nonzero relocation addend requires explicit support')
                if not 0 <= offset <= len(blobs[0]) - 4:
                    raise RuntimeError('relocation outside payload')
                relocations.append((offset, kind, value - bases[0]))
    for name, address in original['symbols'].items():
        prefix = '__Thumbv7ABSLongThunk_'
        if not name.startswith(prefix):
            continue
        target_name = name[len(prefix):]
        if target_name not in ('as_native_near', 'af_native_peak'):
            raise RuntimeError('unreviewed linker thunk')
        offset = (address & ~1) - bases[0]
        if blobs[0][offset+8:offset+10] != bytes.fromhex('6047'):
            raise RuntimeError('linker thunk BX ip mismatch')
        target = original['symbols'][target_name]
        for delta, kind in ((0,47),(4,48)):
            hi,lo = struct.unpack_from('<HH',blobs[0],offset+delta)
            if (lo >> 8) & 15 != 12:
                raise RuntimeError('linker thunk register mismatch')
            relocations.append((offset+delta,kind,target-bases[0]))
    relocations.sort()
    if len({r[0] for r in relocations}) != len(relocations):
        raise RuntimeError('duplicate relocation sites')
    for m, base in zip(manifests, bases):
        if m['source_sha256'] != reviewed or m['end'] - base != len(blobs[0]):
            raise RuntimeError('relocation build shape')
        if any(m['symbols'][k] - base != v - bases[0]
               for k, v in original['symbols'].items() if bases[0] <= (v & ~1) < original['end']):
            raise RuntimeError('symbol layout changed')
    for base, blob in zip(bases, blobs):
        rebuilt = bytearray(blobs[0])
        for offset, kind, relative in relocations:
            if kind == 2:
                value = struct.unpack_from('<I', rebuilt, offset)[0]
                struct.pack_into('<I', rebuilt, offset, value + base - bases[0])
            else:
                hi, lo = struct.unpack_from('<HH', rebuilt, offset)
                if hi & 0xfbf0 != (0xf240 if kind == 47 else 0xf2c0):
                    raise RuntimeError('Thumb MOVW/MOVT opcode mismatch')
                immediate = ((hi & 15) << 12) | ((hi & 0x400) << 1) | ((lo & 0x7000) >> 4) | (lo & 255)
                expected = ((bases[0] + relative) >> (16 if kind == 48 else 0)) & 65535
                if immediate != expected:
                    raise RuntimeError('linked immediate disagrees with object symbol')
                immediate = ((base + relative) >> (16 if kind == 48 else 0)) & 65535
                hi = (hi & ~0x40f) | (immediate >> 12) | ((immediate & 0x800) >> 1)
                lo = (lo & ~0x70ff) | ((immediate & 0x700) << 4) | (immediate & 255)
                struct.pack_into('<HH', rebuilt, offset, hi, lo)
        if rebuilt != blob:
            print('uncovered', hex(base), [(hex(i), rebuilt[i:i+4].hex(), blob[i:i+4].hex()) for i in range(0,len(blob),4) if rebuilt[i:i+4]!=blob[i:i+4]])
            raise RuntimeError('relocated payload differs from independently linked payload')
    rows = ['#pragma once', '#include <stdint.h>',
            '// X1D-50c 1.25.0 固定来源；重定位前必须验证堆块归属。',
            'static const uint32_t hbl_af_template_base = 0x00800000u;',
            'static const uint32_t hbl_af_words[] = {']
    for offset in range(0, len(words[0]), 8):
        rows.append('    ' + ','.join(f'0x{v:08x}u' for v in words[0][offset:offset+8]) + ',')
    rows += ['};', 'static const uint32_t hbl_af_relocations[][3] = {' + ','.join('{'+f'{o},{k},{v}'+'}' for o,k,v in relocations) + '};']
    report = {'schema': 'boot-af-relocation-v1', 'hardwareRequests': 0,
              'sourceSha256': reviewed, 'templateSha256': hashlib.sha256(blobs[0]).hexdigest(),
              'payloadBytes': len(blobs[0]), 'relocationsOffsetKindTarget': relocations,
              'independentLinkBases': bases, 'independentLinkMatches': True,
              'installed': False}
    (OUT / 'af_relocation_data.h').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    (OUT / 'relocation-proof.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))

if __name__ == '__main__':
    main()

