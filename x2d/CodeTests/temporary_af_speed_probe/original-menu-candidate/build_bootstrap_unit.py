"""给固定 MainScreen 编译单元增加一个 Loader；不改原函数和对象索引。离线。"""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parent))
from inspect_menu_resources import load_gui, GUI_SHA


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def strings(data):
    count, table = struct.unpack_from('<II', data, 112)
    result = []
    for i in range(count):
        at = u32(data, table + i * 4)
        length = u32(data, at)
        assert at + 4 + length * 2 + 2 <= len(data)
        result.append(data[at + 4:at + 4 + length * 2].decode('utf-16le'))
    return result


def build(original, source):
    assert original[:8] == b'qv4cdata' and u32(original, 12) == 0x60401
    assert u32(original, 24) == len(original) == 15084
    blob = bytearray(original)
    names = strings(original)
    count, table = struct.unpack_from('<II', original, 112)
    string_offsets = list(struct.unpack_from('<' + str(count) + 'I', original, table))

    def append(data):
        blob.extend(b'\0' * (-len(blob) % 8))
        at = len(blob)
        blob.extend(data)
        blob.extend(b'\0' * (-len(blob) % 8))
        return at

    def name(text):
        if text not in names:
            string_offsets.append(append(struct.pack('<I', len(text.encode('utf-16le'))//2)
                                         + text.encode('utf-16le') + b'\0\0'))
            names.append(text)
        return names.index(text)

    qml = u32(original, 244)
    n, table = struct.unpack_from('<II', original, qml + 8)
    offsets = list(struct.unpack_from('<' + str(n) + 'I', original, qml + table))
    assert n == 13 and qml == 12056
    root = bytearray(original[qml + offsets[0]:qml + offsets[1]])
    bc = struct.unpack_from('<H', root, 46)[0]
    bt = u32(root, 48)
    bindings = root[bt:bt + bc * 24]
    assert bc == 7 and len(root) == 328
    # 原表在副本中保留，新表追加；所有其他对象内相对偏移不变。
    new_bt = len(root)
    root.extend(bindings)
    root.extend(struct.pack('<6I', name(''), 8 << 16, n, 0, 0, 0))
    struct.pack_into('<H', root, 46, bc + 1)
    struct.pack_into('<I', root, 48, new_bt)
    loader = bytearray(84)
    struct.pack_into('<4I', loader, 0, name('Loader'), name(''), 0xffff0000, 0xffffffff)
    struct.pack_into('<H', loader, 46, 2)
    struct.pack_into('<I', loader, 48, 84)
    loader.extend(struct.pack('<6I', name('objectName'), 3 << 16, 0, name('X2dNativeMenuBootstrap'), 0, 0))
    loader.extend(struct.pack('<6I', name('source'), 3 << 16, 0, name(source), 0, 0))
    offsets[0] = append(root) - qml
    offsets.append(append(loader) - qml)
    table = append(struct.pack('<' + str(len(offsets)) + 'I', *offsets))
    struct.pack_into('<II', blob, qml + 8, len(offsets), table - qml)
    st = append(struct.pack('<' + str(len(string_offsets)) + 'I', *string_offsets))
    struct.pack_into('<II', blob, 112, len(string_offsets), st)
    struct.pack_into('<I', blob, 24, len(blob))
    blob[76:92] = hashlib.md5(blob[92:]).digest()
    assert strings(blob) == names
    assert blob[120:236] == original[120:236], 'function/lookup/constant tables changed'
    old_objects = list(struct.unpack_from('<13I', original, qml + u32(original, qml+12)))
    assert offsets[1:13] == old_objects[1:]
    new_root = qml + offsets[0]
    assert blob[new_root+new_bt:new_root+new_bt+bc*24] == bindings
    # 原始单元除头部与 QmlUnit 的对象表指向外没有改写。
    allowed = set(range(24,28)) | set(range(76,92)) | set(range(112,120)) | set(range(qml+8,qml+16))
    assert all(a == b or i in allowed for i, (a,b) in enumerate(zip(original, blob)))
    return bytes(blob)


def main():
    binary = load_gui()
    symbol = next(s for s in binary.symbols if s.name.endswith('32_app_qml_mainmenu_MainScreen_qml7qmlDataE'))
    original = binary.read(symbol['st_value'], symbol['st_size'])
    outputs = {}
    for kind, url in [('device', 'file:///system/etc/X2dNativeMenuBootstrap.qml'),
                      ('host', (D / '.stock-host/Bootstrap.qml').as_uri())]:
        clone = build(original, url)
        path = D / ('main-screen-bootstrap-' + kind + '.bin')
        path.write_bytes(clone)
        outputs[kind] = dict(bytes=len(clone), sha256=hashlib.sha256(clone).hexdigest())
    (D / 'bootstrap-unit-validation.json').write_text(json.dumps(dict(
        firmware='4.2.0', guiSha256=GUI_SHA, originalUnitBytes=len(original),
        originalFunctionsPreserved=True, originalObjectIndicesPreserved=True,
        addedObjects=1, outputs=outputs, deviceValidated=False), indent=2)+'\n')
    print(json.dumps(outputs))


if __name__ == '__main__':
    main()
