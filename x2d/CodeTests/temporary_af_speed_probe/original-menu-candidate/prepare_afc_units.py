"""只读参考仓库的构建函数，在当前候选目录生成并核验 AF-C 两份单元。"""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parent))
from inspect_menu_resources import load_gui, GUI_SHA


def main():
    reference = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(reference / 'firmware-analysis'))
    from qml_unit_dump import Unit
    import build_x2d_controlscreen_afc_unit as control
    import build_x2d_popover_focus_three_items as popover
    binary = load_gui()
    output = D / 'native-package'
    results = {}
    for name, builder, expected in [
        ('control', control, '546755c8c459e4a3d4cc1cf7d677bd521ae62bca9306e18f88bb17c811d00728'),
        ('popover', popover, '0958c3b8b3909228f2fec9e551f8a1fd7f867056810c47b982b1b21fbd830420')]:
        symbol = next(s for s in binary.symbols if s.name.endswith(builder.UNIT_SYMBOL))
        original = binary.read(symbol['st_value'], symbol['st_size'])
        clone = builder.build_clone(Unit(original))
        assert hashlib.sha256(clone).hexdigest() == expected
        assert clone[76:92] == hashlib.md5(clone[92:]).digest()
        # 已有函数均保持相同字节与索引，新增函数只追加。
        count, table = struct.unpack_from('<II', original, 120)
        new_count, new_table = struct.unpack_from('<II', clone, 120)
        assert new_count == count + (name == 'control')
        assert original[table:table+count*4] == clone[new_table:new_table+count*4]
        for i in range(count):
            offset = struct.unpack_from('<I', original, table+i*4)[0]
            code_offset, code_size = struct.unpack_from('<II', original, offset)
            end = offset+code_offset+code_size
            assert clone[offset:end] == original[offset:end]
        for suffix, data in [('stock', original), ('afc', clone)]:
            (output / f'{name}-{suffix}.bin').write_bytes(data)
        results[name] = dict(originalBytes=len(original), cloneBytes=len(clone),
                             cloneSha256=expected, originalFunctionsPreserved=True)
    assert binary.read(0x18a2a64,4) == bytes(4)
    results.update(guiSha256=GUI_SHA, staticValidation=True, deviceValidated=False,
                   focusOrder=['AF-S','AF-C','MF'], popoverItems=3,
                   reference='shared research build functions; read only; exact clone hashes matched')
    (D/'afc-unit-validation.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
