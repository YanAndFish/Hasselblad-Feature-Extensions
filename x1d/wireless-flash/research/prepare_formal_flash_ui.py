"""固定 X1D 1.25.0 的正式引闪页离线资源候选；不导入设备会话，不安装。"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / 'build/formal-flash-ui'
sys.path.insert(0, str(HERE))
import build as common

ASSETS = ('EVF_ArrowLeft.png', 'EVF_ArrowRight.png', 'FlashStatus.png',
          'settings_icon.png', 'ControlScreen_WiFi.png', 'left_bracket.png', 'right_bracket.png')


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('原厂插入锚点不唯一或已改变')
    return text.replace(before, after, 1)


def read_assets(gui):
    result = {}
    for tree, names, data in [(0x10C75C, 0x10C5E8, 0x94E20), (0x1EC7F0, 0x1E7E44, 0x10C7F8)]:
        pending = [(0, '')]
        seen = set()
        while pending:
            index, parent = pending.pop()
            if index in seen or len(seen) > 10000:
                raise ValueError('资源树边界不合法')
            seen.add(index)
            entry = gui.read(tree + index*14, 14)
            offset, flags = struct.unpack_from('>IH', entry)
            length = struct.unpack('>H', gui.read(names+offset, 2))[0]
            if length > 1024:
                raise ValueError('资源名称超长')
            name = gui.read(names+offset+6, length*2).decode('utf-16-be') if index else ''
            path = parent+'/'+name if name else parent
            if flags & 2:
                count, child = struct.unpack_from('>II', entry, 6)
                if count > 10000:
                    raise ValueError('资源子项超长')
                pending.extend((i, path) for i in range(child, child+count))
            elif path in ('/icons/'+a for a in ASSETS):
                offset = struct.unpack_from('>I', entry, 10)[0]
                size = struct.unpack('>I', gui.read(data+offset, 4))[0]
                if size > 1_000_000:
                    raise ValueError('图标资源过大')
                content = gui.read(data+offset+4, size)
                if flags & 1:
                    wanted = struct.unpack_from('>I', content)[0]
                    content = zlib.decompress(content[4:])
                    if wanted != len(content):
                        raise ValueError('图标展开长度不符')
                if not content.startswith(b'\x89PNG\r\n\x1a\n') or path in result:
                    raise ValueError('图标格式或唯一性不符')
                result[path] = content
    if len(result) != len(ASSETS):
        raise ValueError('未找到全部原生图标')
    return result


def build():
    if Path.cwd().resolve() != ROOT:
        raise ValueError('只允许在本任务工作目录构建')
    raw = (common.BASELINE/'usr/bin/victory-gui').read_bytes()
    if common.sha(raw) != common.GUI_SHA:
        raise ValueError('GUI 必须匹配固定官方 1.25.0 基线')
    gui = common.ArmElf(raw)
    original = common.qml_files(gui)
    source = HERE/'ui/formal'
    swipe = (source/'ControlSwipe.qml.inc').read_text(encoding='utf-8')
    control = original['/controlscreen/ControlScreen.qml']
    control = replace_once(control, '    id: scope', '    id: scope\n    clip: true')
    control = replace_once(control, 'property bool preventSwipe: popupOpen || Camera.inSession',
                           'property bool preventSwipe: popupOpen || Camera.inSession || formalFlashSwipe.secondPage || formalFlashSwipe.drag.active')
    control = replace_once(control, '        objectName: "ControlScreen_root"',
                           '        objectName: "ControlScreen_root"\n        parent: formalFlashTrack')
    control = control[:control.rfind('}')] + swipe + '\n}\n'
    edited = {'/controlscreen/ControlScreen.qml': control}
    for name in ('FlashPage.qml', 'FlashIconButton.qml', 'FlashText.qml', 'FlashValueText.qml', 'FlashLampIcon.qml', 'FlashStyle.qml', 'FlashToggleRow.qml'):
        edited['/controlscreen/'+name] = (source/name).read_text(encoding='utf-8')
    for name, text in edited.items():
        target = OUT/'qml'/name.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    icons = read_assets(gui)
    for name, data in icons.items():
        target = OUT/'baseline-assets'/Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    bundle = common.rcc(edited)
    (OUT/'formal-ui.rcc').write_bytes(bundle)
    report = {
        'kind': 'native-qml-formal-flash-ui-candidate',
        'firmwareSource': 'official X1D 1.25.0', 'guiSha256': common.GUI_SHA,
        'originalControlSha256': common.sha(original['/controlscreen/ControlScreen.qml'].encode()),
        'files': {name: common.sha(data.encode()) for name, data in edited.items()},
        'icons': {name: common.sha(data) for name, data in icons.items()},
        'sourceFiles': {str(p.relative_to(HERE)):common.sha(p.read_bytes()) for p in sorted(source.iterdir()) if p.is_file()},
        'builderSha256': common.sha(Path(__file__).read_bytes()),
        'rccSha256': common.sha(bundle), 'rccVersion': 1,
        'entry': 'control-screen-swipe-left', 'return': 'swipe-right-or-back-icon',
        'originalExposureAndFlashCompensationUnchanged': True,
        'groupSettings': 'local-drafts-only', 'deviceAdapterImplemented': False,
        'uiGroupLabels': list('ABCDEF0123456789'),
        'extendedRadioGroupSupportVerified': False,
        'modelingLamp': 'local-ui-draft-only',
        'deliveryOptions': {'sendPowerUpdates': True, 'sendFlashSync': True, 'defaultMasterEnabled': False},
        'deliveryPolicy': 'independent-power-and-sync-request-gates-no-device-adapter',
        'disabledSyncPreservesFactoryHotshoePath': True,
        'testFlashRequiresSyncOption': True,
        'style': 'shared-spacing-type-and-button-components',
        'groupSelection': 'session-local-display-preference',
        'allGroupAdjustment': 'selected-groups-only-atomic-at-power-limits-preserve-enabled-state',
        'installed': False, 'cameraRequests': 0, 'radioRequests': 0,
        'powerWorkResumed': False, 'qmlTargetRuntimeValidated': False,
        'reference': 'https://www.godox.com/product-e/X3Pro.html',
    }
    (OUT/'candidate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    result = build()
    print(json.dumps({'built': True, 'qmlFiles': len(result['files']), 'originalIcons': len(result['icons']),
                      'installed': False, 'cameraRequests': 0}, ensure_ascii=False))
