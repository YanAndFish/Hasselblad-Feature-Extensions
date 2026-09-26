"""生成机内逐字核对用的紧凑基线；不生成安装器，不访问相机。"""
import hashlib
import json
from pathlib import Path
import re
import struct

BASE = Path(__file__).resolve().parent


def rows(text, name, fields):
    body = text.split(name + '[] = {', 1)[1].split('};', 1)[0]
    result = [tuple(int(x, 16) for x in re.findall(r'0x([0-9a-f]+)u', row))
              for row in re.findall(r'\{([^{}]+)\}', body)]
    assert result and all(len(row) == fields for row in result)
    return result


def pack(values):
    """1字节标记：高位为重复字，低7位+1为字数；其后为小端字。"""
    out = bytearray()
    i = 0
    while i < len(values):
        run = 1
        while i + run < len(values) and run < 128 and values[i + run] == values[i]:
            run += 1
        if run >= 2:
            out.append(0x80 | (run - 1))
            out.extend(struct.pack('<I', values[i]))
            i += run
        else:
            start = i
            i += 1
            while i < len(values) and i - start < 128:
                if i + 1 < len(values) and values[i] == values[i + 1]:
                    break
                i += 1
            out.append(i - start - 1)
            out.extend(struct.pack('<' + 'I' * (i - start), *values[start:i]))
    return bytes(out)


def build():
    source = BASE / 'build/boot-data/boot_contract_data.h'
    text = source.read_text(encoding='utf-8')
    expected = {}
    for name in ['hbl_boot_expected', 'hbl_flash_expected']:
        for address, value in rows(text, name, 2):
            assert address not in expected or expected[address] == value
            expected[address] = value
    for address in range(0x2b2800, 0x2b2840, 4):
        assert address not in expected or expected[address] == 0
        expected[address] = 0
    flash_words = text.split('hbl_flash_words[] = {', 1)[1].split('};', 1)[0]
    flash_size = len(re.findall(r'0x[0-9a-f]+u', flash_words)) * 4
    for address in range(0x2b2880, 0x2b2880 + flash_size, 4):
        assert address not in expected or expected[address] == 0
        expected[address] = 0
    groups = []
    for address, value in sorted(expected.items()):
        if not groups or address != groups[-1][0] + 4 * len(groups[-1][1]):
            groups.append((address, []))
        groups[-1][1].append(value)
    guards = sorted(set(rows(text, 'hbl_boot_guards', 3) + rows(text, 'hbl_flash_guards', 3)))
    blob = bytearray()
    descriptors = []
    for address, values in groups:
        encoded = pack(values)
        descriptors.append((address, len(values), len(blob), len(encoded)))
        blob.extend(encoded)
    output = BASE / 'build/fast-start-research'
    output.mkdir(parents=True, exist_ok=True)
    header = ['/* 固定 X1D 1.25.0 基线；由 build_fast_baseline.py 生成。 */',
              'static const unsigned char fast_bytes[] = {']
    for i in range(0, len(blob), 24):
        header.append(','.join(str(b) for b in blob[i:i+24]) + ',')
    header += ['};', 'static const struct FastRange fast_ranges[] = {']
    header += ['{%s},' % ','.join(str(v) + 'u' for v in row) for row in descriptors]
    header += ['};', 'static const struct FastGuard fast_guards[] = {']
    header += ['{%s},' % ','.join(str(v) + 'u' for v in row) for row in guards]
    header += ['};', '']
    (output / 'fast_baseline_data.h').write_text('\n'.join(header), encoding='utf-8')
    report = {'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'wordCount': len(expected), 'ranges': len(groups), 'guards': len(guards),
              'encodedBytes': len(blob), 'descriptorBytes': 16 * len(groups),
              'guardBytes': 12 * len(guards),
              'scope': 'exact memory comparison only; firmware identity, ownership, transfer, cache, installation and timing not implemented'}
    (output / 'fast-baseline-manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return expected, guards, report


if __name__ == '__main__':
    print(json.dumps(build()[2]))
