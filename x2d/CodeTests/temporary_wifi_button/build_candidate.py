"""固定 X2D 4.2.0 的临时空按钮候选；仅生成本地差分，不访问相机。"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import zlib

X2D = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(X2D / 'tools'))
from inspect_gui_entry_4_2_0 import GUI_SHA, system_elf

FOOTER = '''
        footer: Item {
            objectName: "temporaryWifiButtonFooter"
            width: list.width
            height: root.menuLabel === "Wi-Fi" ? root.heightForItem : 0
            visible: height > 0
            Rectangle {
                anchors.centerIn: parent
                width: parent.width - 2 * Constants.settingsMenuSettingLeftMargin
                height: parent.height * 0.78
                radius: 8 * Constants.scaleFactor
                color: emptyButtonMouse.pressed ? "#404040" : "#242424"
                border.color: "#909090"
                Text {
                    anchors.centerIn: parent
                    text: "临时测试按钮"
                    color: "white"
                    font.family: Constants.settingsMenuButtonFontName
                    font.pixelSize: 28 * Constants.scaleFactor
                }
                MouseArea {
                    id: emptyButtonMouse
                    objectName: "temporaryWifiButtonMouse"
                    anchors.fill: parent
                    onClicked: {}
                }
            }
        }
'''


def file_offset(binary, address):
    for segment in binary.elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD' and segment['p_vaddr'] <= address < segment['p_vaddr'] + segment['p_filesz']:
            return address - segment['p_vaddr'] + segment['p_offset']
    raise ValueError('地址不在文件映射中')


def main():
    binary = system_elf('/bin/camera-gui', GUI_SHA)
    tree, names, data, node = 0x18e4208, 0x18e5be6, 0x18e8cfa, 68
    row = binary.read(tree + node * 22, 22)
    name_offset, flags = struct.unpack_from('>IH', row)
    name_length = struct.unpack('>H', binary.read(names + name_offset, 2))[0]
    assert binary.read(names + name_offset + 6, name_length * 2).decode('utf-16-be') == 'SettingsGeneric.qml'
    assert flags == 1
    address = data + struct.unpack_from('>I', row, 10)[0]
    old_size = struct.unpack('>I', binary.read(address, 4))[0]
    original = binary.read(address + 4, old_size)
    source = zlib.decompress(original[4:]).decode('utf-8')
    assert len(source.encode()) == struct.unpack('>I', original[:4])[0]
    anchor = '        // Section header\n'
    assert source.count(anchor) == 1 and 'footer:' not in source
    # 只去掉开头的说明注释，为新增控件保留原资源分配空间。
    assert source.startswith('/*')
    candidate = source[source.index('*/') + 2:]
    comment_start = candidate.index('    /* The menu contains delegates')
    comment_end = candidate.index('*/', comment_start) + 2
    candidate = candidate[:comment_start] + candidate[comment_end:]
    candidate = candidate.replace(anchor, FOOTER + '\n' + anchor)
    raw = candidate.encode('utf-8')
    compressed = struct.pack('>I', len(raw)) + zlib.compress(raw, 9)
    assert len(compressed) <= old_size, (len(compressed), old_size)
    resource_patch = struct.pack('>I', len(compressed)) + compressed + bytes(old_size - len(compressed))
    # 只使这个 QML 单元的预编译头失效；Qt 的 verifyHeader 失败分支返回空缓存。
    # 是否能成功回退源 QML 仍须独立验证，不能仅凭此生成器标记装机通过。
    cache_address = 0x17cbe50
    assert binary.read(cache_address, 8) == b'qv4cdata'
    patches = [
        (file_offset(binary, address), binary.read(address, old_size + 4), resource_patch),
        (file_offset(binary, cache_address), b'q', b'X'),
    ]
    modified = bytearray(binary.data)
    for offset, before, after in patches:
        assert len(before) == len(after) and modified[offset:offset + len(before)] == before
        modified[offset:offset + len(after)] = after
    out = X2D / 'outputs/4.2.0/temporary-wifi-button'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'SettingsGeneric.qml').write_text(candidate, encoding='utf-8')
    manifest = {'firmware': '4.2.0', 'sourceSha256': GUI_SHA,
                'candidateSha256': hashlib.sha256(modified).hexdigest(),
                'deviceAccesses': 0, 'installed': False, 'patches': []}
    for number, (offset, before, after) in enumerate(patches):
        filename = f'patch-{number}.bin'
        (out / filename).write_bytes(after)
        manifest['patches'].append({'offset': offset, 'length': len(after), 'file': filename,
                                    'beforeSha256': hashlib.sha256(before).hexdigest(),
                                    'afterSha256': hashlib.sha256(after).hexdigest()})
    (out / 'candidate.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'candidateCreated': True, 'originalCompressedBytes': old_size,
                      'candidateCompressedBytes': len(compressed), 'installed': False}))


if __name__ == '__main__':
    main()
