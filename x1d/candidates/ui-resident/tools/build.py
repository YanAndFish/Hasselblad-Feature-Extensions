"""固定 1.25.0 QRC 文本的可组合补丁；只写本候选目录，无设备接口。"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'x1d/tools'))
from binary import ArmElf, qml_files
from resource_bundle import rcc

GUI_HASH = 'd29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
PATHS = ('/mainmenu/MainScreen.qml', '/mainmenu/Menu.qml', '/settings/SettingsGeneric.qml')

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('补丁锚点缺失或重复：' + old[:90])
    return text.replace(old, new, 1)

def gate_connections(path, text):
    # Qt 5.5 无 Connections.enabled；null target 在关闭时真正断开连接。
    # 用原 target 与首个 handler 的组合定位；不修改其他候选追加的 Connections。
    expected = {
        PATHS[1]: [('entry_loader.item','onVisibleChanged'), ('cambody','onCapabilitiesChanged'),
                   ('suc','onCambody_attachedChanged'), ('configstore','onExpModeChanged')],
        PATHS[2]: [('subDialog.item','onLeftSelected'), ('farm','onResetGlobalImageSequenceCounterSucceeded'),
                   ('delegate_item.customProfile.length > 0 ? subDialog.item : null','onRightSelected'),
                   ('delegate_item.fwRetryPressed ? subDialog.item : null','onRightSelected'),
                   ('guiconfig','onShowSecretMenuItemsChanged'), ('configstore','onExpModeChanged'),
                   ('Lens','onLens_familyChanged'), ('configstore','onFocusSizeChanged')],
    }[path]
    pattern = r'(Connections\s*\{\s*target: )([^\n]+)(\n(?:(?:[ \t]*//[^\n]*\n)|\s)*)(on\w+):'
    matches = list(re.finditer(pattern, text))
    for target, handler in expected:
        found = [m for m in matches if (m[2], m[4]) == (target,handler)]
        if len(found) != 1:
            raise ValueError('原厂连接锚点缺失或重复：'+target+' / '+handler)
    for m in reversed(matches):
        if (m[2],m[4]) in expected:
            text = text[:m.start(2)]+'root.residentPresented ? ('+m[2]+') : null'+text[m.end(2):]
    return text

def transform(path, text):
    if 'residentPresented' in text or 'ResidentLoader {' in text:
        raise ValueError('已存在常驻补丁，拒绝重复叠加')
    if path == PATHS[0]:
        text = replace_once(text, '        Loader {\n            id: menu_loader',
            '        ResidentLoader {\n            residentSource: "qrc:///mainmenu/Menu.qml"\n            id: menu_loader')
        start = text.index('    // This loader pre-load SettingsGeneric')
        end = text.index('\n    }', start) + len('\n    }')
        original = text[start:end]
        if 'source = ""' not in original or 'settingsGeneric_Loader' not in original:
            raise ValueError('旧编译缓存块不匹配')
        text = text[:start] + '    // Menu 内的 ResidentLoader 持有真正的 SettingsGeneric 实例。' + text[end:]
    elif path == PATHS[1]:
        text = replace_once(text, '    property variant lastItems;', '    property variant lastItems: [];')
        text = replace_once(text, '    function populateModel(menuItemValues)', '''    property bool residentPresented: true
    property var residentHost: null
    function residentActivate() {
        residentDeactivate()
        residentPresented = true
    }
    function residentDeactivate() {
        residentPresented = false
        entry_loader.active = false
        entry_loader.scrollToSubmenuItem = ""
        listMenuTimer.stop()
        list.highlightAllow = false
        list.currentIndex = -1
        list.lastIndex = -1
        list.contentY = 0
        menu_model.clear()
        lastItems = []
        focus = false
    }

    function populateModel(menuItemValues)''')
        text = replace_once(text, '        lastItems = menuItemValues', '        if (!residentPresented) return\n        lastItems = menuItemValues')
        text = replace_once(text, '    onFocusChanged: {\n        if(focus)\n', '    onFocusChanged: {\n        if(focus && residentPresented)\n')
        text = replace_once(text, '        Loader {\n            id: entry_loader',
            '        ResidentLoader {\n            residentSource: "qrc:///settings/SettingsGeneric.qml"\n            id: entry_loader')
        text = replace_once(text, '        entry_loader.source = itemFile', '        entry_loader.setSource(itemFile, {})')
        text = replace_once(text, '                root.parent.visible = true', '                (root.residentHost || root.parent).visible = true')
        text = replace_once(text, '                    if (!target.visible)', '                    if (!entry_loader.transitioning && target && !target.visible)')
        text = replace_once(text, '        entry_loader.scrollToSubmenuItem = itemName', '''        entry_loader.scrollToSubmenuItem = itemName
        if (entry_loader.item && typeof entry_loader.item.scrollToItem === "function") {
            entry_loader.item.scrollToItem(itemName)
            entry_loader.scrollToSubmenuItem = ""
        }''')
        text = gate_connections(path, text)
    elif path == PATHS[2]:
        text = replace_once(text, '\n    property var itemValues\n', '\n    property var itemValues: ""\n')
        text = replace_once(text, '    function populateModel(newItemValues)', '''    property bool residentPresented: true
    property var residentHost: null
    function residentActivate() {
        residentDeactivate()
        residentPresented = true
        list.focus = true
    }
    function residentDeactivate() {
        residentPresented = false
        listTimer.stop()
        dropDownSelector.close()
        subDialog.active = false
        confirmDialog.active = false
        informDialog.close()
        informDialog.visible = false
        informDialog.closeDialog = false
        list.highlightAllow = false
        list.currentIndex = -1
        list.lastIndex = -1
        list.contentY = 0
        list.section.property = ""
        listModel.clear()
        itemValues = ""
        list.focus = false
        focus = false
    }

    function populateModel(newItemValues)''')
        text = replace_once(text, '        listModel.clear();', '        if (!residentPresented) return\n        list.section.property = ""\n        listModel.clear();')
        text = replace_once(text, '            if (!visible) {', '            if (!visible && root.residentPresented) {')
        if text.count('list.forceActiveFocus()') != 3:
            raise ValueError('设置页焦点恢复锚点数量已变化，需先审阅组合修改')
        text = text.replace('list.forceActiveFocus()', 'if (root.residentPresented) list.forceActiveFocus()')
        text = gate_connections(path, text)
    else:
        raise ValueError('非白名单资源')
    return text

def baseline():
    gui = ArmElf.load('usr/bin/victory-gui')
    if hashlib.sha256(gui.data).hexdigest() != GUI_HASH:
        raise ValueError('1.25.0 原 GUI 哈希不匹配')
    return qml_files(gui)

def compose(resources):
    """给协调方的纯函数接口：保留输入全部资源，只补丁三文件并增加一个组件。"""
    if '/mainmenu/ResidentLoader.qml' in resources:
        raise ValueError('已有 ResidentLoader，拒绝覆盖或重复组合')
    original = baseline()
    result = dict(resources)
    updated = {p: transform(p, resources.get(p, original[p])) for p in PATHS}
    updated['/mainmenu/ResidentLoader.qml'] = (HERE/'qml/mainmenu/ResidentLoader.qml').read_text(encoding='utf-8')
    result.update(updated)
    return result

def build(input_dir=None, output=None):
    output = Path(output or HERE / 'build/overlay').resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('输出必须位于独立 ui-resident 候选目录')
    if input_dir:
        input_dir = Path(input_dir).resolve()
        if not input_dir.is_relative_to(ROOT):
            raise ValueError('组合输入必须位于当前 Hasselblad 工作区')
        if output == input_dir or output.is_relative_to(input_dir):
            raise ValueError('组合输入为只读，输出不得位于输入目录内')
        if (input_dir/'mainmenu/ResidentLoader.qml').exists():
            raise ValueError('组合输入已包含 ResidentLoader')
    original = baseline()
    sources = {p: (Path(input_dir) / p.lstrip('/')).read_text(encoding='utf-8')
               if input_dir and (input_dir / p.lstrip('/')).is_file() else original[p] for p in PATHS}
    changed = {p: transform(p, sources[p]) for p in PATHS}
    changed['/mainmenu/ResidentLoader.qml'] = (HERE / 'qml/mainmenu/ResidentLoader.qml').read_text(encoding='utf-8')
    # 在任何输出前完成所有锚点检查。只输出四个资源，不复制 main.qml 或冻结包。
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'firmware': 'X1D 1.25.0', 'guiSha256': GUI_HASH,
                'offlineOnly': True, 'installed': False, 'resources': {}}
    diff = []
    for p, content in changed.items():
        dest = output / p.lstrip('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding='utf-8', newline='\n')
        before = sources.get(p, '')
        manifest['resources'][p] = {'inputSha256': hashlib.sha256(before.encode()).hexdigest(),
                                   'outputSha256': hashlib.sha256(content.encode()).hexdigest()}
        diff.extend(difflib.unified_diff(before.splitlines(True), content.splitlines(True),
                    fromfile='a'+p, tofile='b'+p))
    (output / 'changes.patch').write_text(''.join(diff), encoding='utf-8')
    bundle = rcc(changed)
    (output / 'ui-resident.rcc').write_bytes(bundle)
    manifest['resourceBundle'] = {'file':'ui-resident.rcc', 'version':1, 'bytes':len(bundle),
                                  'sha256':hashlib.sha256(bundle).hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, help='可组合的现有 QRC 文本目录，只读')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.input_dir, args.output), ensure_ascii=False, indent=2))
