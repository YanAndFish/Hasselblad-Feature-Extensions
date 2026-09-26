"""只读分析官方 1.25.0 的板级配置；仅在实验 build 目录输出报告。"""
from pathlib import Path
import hashlib
import json
import struct

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / '.research-cache/x1d-1.25.0/baseline'
WEDGE_SHA = 'bcd548efc1c01eb93bb8c8829beb371e2991f42dc7fcdf8bae29fa66d7bc7aca'


def parse(data):
    if len(data) < 40:
        raise ValueError('FDT header truncated')
    h = struct.unpack_from('>10I', data)
    if h[0] != 0xd00dfeed or h[1] != len(data):
        raise ValueError('FDT header mismatch')
    pos, end = h[2], h[2] + h[9]
    strings = data[h[3]:h[3] + h[8]]
    if end > len(data) or len(strings) != h[8]:
        raise ValueError('FDT sections truncated')
    stack, nodes = [], {}
    while pos + 4 <= end:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            stop = data.index(0, pos, end)
            stack.append(data[pos:stop].decode('ascii'))
            pos = (stop + 4) & ~3
            nodes['/'.join(stack)] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            if pos + 8 > end or not stack:
                raise ValueError('FDT property header invalid')
            size, offset = struct.unpack_from('>II', data, pos)
            pos += 8
            if pos + size > end or offset >= len(strings):
                raise ValueError('FDT property truncated')
            name = strings[offset:strings.index(0, offset)].decode('ascii')
            nodes['/'.join(stack)][name] = data[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 9:
            if stack:
                raise ValueError('FDT unclosed node')
            return nodes
        elif token != 4:
            raise ValueError('FDT token invalid')
    raise ValueError('FDT end missing')


def cells(value):
    if len(value) % 4:
        raise ValueError('unaligned cells')
    return struct.unpack('>' + str(len(value) // 4) + 'I', value)


def describe(value):
    if value and value[-1] == 0 and all(x == 0 or 32 <= x < 127 for x in value):
        return value.rstrip(b'\0').decode('ascii').split('\0')
    return [hex(x) for x in cells(value)] if len(value) % 4 == 0 else value.hex()


def analyze(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if 'wedge' in path.name and digest != WEDGE_SHA:
        raise ValueError('fixed Wedge source changed')
    nodes = parse(data)
    handles = {cells(d['phandle'])[0]: n for n, d in nodes.items() if 'phandle' in d}
    selected = {}
    for name, props in nodes.items():
        if not any(t in name for t in ('serial@', '/usb@', '/pcie@', '/aliases')):
            continue
        entry = {k: describe(v) for k, v in props.items()}
        pins = []
        for handle in cells(props.get('pinctrl-0', b'')):
            group = handles[handle]
            raw = cells(nodes[group].get('fsl,pins', b''))
            if len(raw) % 6:
                raise ValueError('pin tuples invalid')
            pins.append({'group': group, 'tuples': [[hex(x) for x in raw[i:i+6]] for i in range(0, len(raw), 6)]})
        entry['resolved_pins'] = pins
        for key in ('power-on-gpio', 'reset-gpio'):
            if key in props:
                values = cells(props[key])
                entry[key + '-controller'] = handles.get(values[0], 'unresolved')
        selected[name] = entry
    return {'source': str(path.relative_to(BASE)), 'sha256': digest, 'nodes': selected}


if __name__ == '__main__':
    report = {'source_firmware': 'official X1D 1.25.0', 'camera_access': False,
              'physical_connections_proven': False,
              'boards': [analyze(p) for p in sorted((BASE / 'boot').glob('*.dtb'))]}
    output = HERE / 'build/board-topology.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'boards': len(report['boards']), 'output': str(output), 'camera_access': False}))
