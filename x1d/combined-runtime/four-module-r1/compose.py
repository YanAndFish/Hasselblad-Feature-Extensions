"""离线读取已冻结资源，生成唯一 RCC；不导入设备模块或执行独立安装器。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'build'
GUI_SHA = 'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
SOURCES = {
    'flash': ('x1d/wireless-flash/build/formal-runtime-ui/formal-ui.rcc',
              '5506d7e5661a7e29e6ca63731d377e1e397c61e7853db2db480a05776cec68c4'),
    'ui': ('x1d/candidates/ui-resident/revisions/full-pages-r2/build/resources/ui-resident.rcc',
           '1c794a21fe7f61a4bdab50f40b5eb02bc428fcd584e9ed2d9d8119c97223b551'),
    'replay': ('x1d/candidates/replay-page-resident/build/session/fixed/cf0515438f7f649d/replay-page.rcc',
               'cf0515438f7f649de95df5d9e735b36145e1f9ed38d6c31364dd9c2a87b17e02'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_rcc(blob):
    if len(blob) < 20 or blob[:4] != b'qres':
        raise ValueError('RCC header')
    version, tree, data, names = struct.unpack_from('>IIII', blob, 4)
    if version != 1 or not 20 <= data <= names <= tree < len(blob) or (len(blob)-tree) % 14:
        raise ValueError('RCC layout')
    count = (len(blob)-tree)//14
    seen, files = set(), {}

    def walk(index, parent):
        if index in seen or not 0 <= index < count:
            raise ValueError('RCC tree cycle/range')
        seen.add(index)
        offset = tree + 14*index
        name_offset, flags = struct.unpack_from('>IH', blob, offset)
        pos = names + name_offset
        if not names <= pos <= tree-6:
            raise ValueError('RCC name range')
        length = struct.unpack_from('>H', blob, pos)[0]
        if pos+6+length*2 > tree:
            raise ValueError('RCC name length')
        name = blob[pos+6:pos+6+length*2].decode('utf-16-be')
        if (index == 0 and name) or (index != 0 and (not name or name in ('.', '..') or '/' in name or '\\' in name)):
            raise ValueError('RCC path')
        path = parent+'/'+name if index else ''
        if flags == 2:
            n, start = struct.unpack_from('>II', blob, offset+6)
            if start+n > count:
                raise ValueError('RCC children')
            for child in range(start, start+n):
                walk(child, path)
        elif flags in (0, 1):
            country, language, position = struct.unpack_from('>HHI', blob, offset+6)
            if country != 0 or language != 1 or path in files:
                raise ValueError('RCC duplicate or localized resource')
            pos = data+position
            if not data <= pos <= names-4:
                raise ValueError('RCC payload range')
            n = struct.unpack_from('>I', blob, pos)[0]
            if pos+4+n > names or n > 4*1024*1024:
                raise ValueError('RCC payload length')
            raw = blob[pos+4:pos+4+n]
            if flags:
                if len(raw) < 4:
                    raise ValueError('RCC compressed header')
                expected = struct.unpack_from('>I', raw)[0]
                if expected > 4*1024*1024:
                    raise ValueError('RCC expanded bound')
                decoder = zlib.decompressobj()
                expanded = decoder.decompress(raw[4:], expected+1)
                if not decoder.eof or decoder.unused_data or len(expanded) != expected:
                    raise ValueError('RCC compressed length')
                raw = expanded
            files[path] = raw.decode('utf-8')
        else:
            raise ValueError('RCC unsupported flags')
    walk(0, '')
    if len(seen) != count:
        raise ValueError('RCC unreachable nodes')
    return files


def merge(modules):
    result, owners = {}, {}
    for owner, values in modules.items():
        for key, value in values.items():
            if key in result:
                raise ValueError('resource conflict: '+key+' ('+owners[key]+', '+owner+')')
            result[key], owners[key] = value, owner
    return result, owners


def build():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Hasselblad workspace required')
    modules = {}
    for name, (path, expected) in SOURCES.items():
        blob = (ROOT/path).read_bytes()
        if digest(blob) != expected:
            raise ValueError('fixed resource changed: '+name)
        modules[name] = read_rcc(blob)
    if {key: len(value) for key, value in modules.items()} != {'flash': 11, 'ui': 6, 'replay': 7}:
        raise ValueError('resource scope changed')
    values, owners = merge(modules)
    if any('/af-settings/' in name for name in values):
        raise ValueError('release AF must not include test UI')
    writer_path = ROOT/'x1d/candidates/ui-resident/tools/resource_bundle.py'
    spec = importlib.util.spec_from_file_location('four_module_rcc_writer', writer_path)
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)
    blob = writer.rcc(values)
    if read_rcc(blob) != values:
        raise ValueError('merged RCC roundtrip')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'combined-ui.rcc').write_bytes(blob)
    for name, value in values.items():
        destination = OUT/'qml'/name.lstrip('/')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value, encoding='utf-8', newline='\n')
    report = {
        'schema': 'x1d-four-module-resources-v1', 'firmware': 'X1D 1.25.0',
        'guiSha256': GUI_SHA, 'rccSha256': digest(blob), 'rccBytes': len(blob),
        'resources': {key: {'owner': owners[key], 'sha256': digest(value.encode())} for key, value in values.items()},
        'sources': {path: sha for path, sha in SOURCES.values()},
        'generatorSources': {str(p.relative_to(ROOT)).replace('\\','/'): digest(p.read_bytes()) for p in (Path(__file__), writer_path)},
        'afProfile': 'release-without-test-ui', 'conflicts': [],
        'hardwareRequests': 0, 'targetValidated': False,
    }
    (OUT/'resources.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return {key: report[key] for key in ('rccSha256','rccBytes','conflicts','hardwareRequests','targetValidated')}


if __name__ == '__main__':
    print(json.dumps(build()))
