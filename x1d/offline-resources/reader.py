"""离线 Qt RCC v1 文本读取，不包含任何原厂资源。"""
import struct
import zlib

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
