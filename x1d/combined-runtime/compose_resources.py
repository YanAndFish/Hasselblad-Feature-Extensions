"""统一资源组合：引闪修正、AF 独立菜单、回放接入，最后常驻 UI。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FLASH = ROOT / 'x1d/wireless-flash'
REPLAY = ROOT / 'x1d/candidates/replay-next'
AF = ROOT / 'x1d/af-experiment/camera-settings-r1'
RESIDENT = ROOT / 'x1d/candidates/ui-resident'
OUT = HERE / 'build/resources'
AF_MENU = '/settings/scripts/MenuItemSpecificationsWedge.js'
AF_ENTRY = 'cameraSettingsAdvancedAF'
AF_ANCHOR = '        {settingsList: "cameraSettingsAutofocus",       itemText:QT_TRANSLATE_NOOP("MENUS", "Autofocus"),           itemFile:"qrc:///settings/SettingsGeneric.qml", demo: false, largeIcon: "LargeIconAutofocus"},'
RESIDENT_SOURCE_SHA = '915fdf996a40dc88a319c431a5b0402b9d37e2598de09470624e45d829002753'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def module(name, path):
    old = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(name, path)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result
    finally:
        sys.path[:] = old


def compose_flash_af(flash_files, original):
    af = module('hbl_combined_af_resources', AF / 'compose_resources.py')
    before = dict(flash_files)
    result = af.compose(flash_files)
    if flash_files != before or any(result[key] != text for key, text in before.items()):
        raise ValueError('AF 组合改变既有资源')
    if set(result) - set(before) != {'/af-settings/SettingsPage.qml'}:
        raise ValueError('AF 资源范围改变')
    menu = result.get(AF_MENU, original[AF_MENU])
    if menu.count(AF_ANCHOR) != 1 or AF_ENTRY in menu:
        raise ValueError('原厂相机菜单锚点改变或已接入 AF')
    entry = '        {settingsList: "'+AF_ENTRY+'", itemText:"AF 设置", itemFile:"qrc:///af-settings/AfSettingsHost.qml", demo:false, largeIcon:"LargeIconAutofocus"},'
    result[AF_MENU] = menu.replace(AF_ANCHOR, AF_ANCHOR + '\n' + entry, 1)
    result['/af-settings/AfSettingsHost.qml'] = (HERE / 'qml/AfSettingsHost.qml').read_text(encoding='utf-8')
    return result


def build():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('workspace mismatch')
    sys.path.insert(0, str(FLASH / 'research'))
    import prepare_formal_runtime_ui as formal
    # 仅从正式构建器列出的生产路径取文本；不能递归收集测试 Harness。
    report = formal.build_resources()
    flash_files = {name: (formal.OUT / 'qml' / name.lstrip('/')).read_text(encoding='utf-8') for name in report['qml']}
    if {name: digest(text.encode()) for name, text in flash_files.items()} != report['qml']:
        raise ValueError('引闪生产资源在组合时改变')
    original = formal.common.qml_files(formal.common.ArmElf((formal.common.BASELINE / 'usr/bin/victory-gui').read_bytes()))
    result = compose_flash_af(flash_files, original)
    replay = module('hbl_combined_replay_resources', REPLAY / 'tools/compose_joint_resources.py')
    before_replay = dict(result)
    result = replay.compose(result)
    if before_replay['/main.qml'].rstrip()[:-1] not in result['/main.qml']:
        raise ValueError('回放没有保留原主资源正文')
    if any(result[key] != text for key, text in before_replay.items() if key != '/main.qml'):
        raise ValueError('回放更改非主资源')
    resident_tool = RESIDENT / 'tools/build.py'
    if digest(resident_tool.read_bytes()) != RESIDENT_SOURCE_SHA:
        raise ValueError('常驻 UI 固定组合器改变')
    resident = module('hbl_combined_resident_resources', resident_tool)
    before_resident = dict(result)
    result = resident.compose(result)
    touched = set(resident.PATHS) | {'/mainmenu/ResidentLoader.qml'}
    if set(result) - set(before_resident) - touched or any(result[key] != text for key, text in before_resident.items() if key not in touched):
        raise ValueError('常驻 UI 更改授权四资源之外的内容')
    if any(result[key] != text for key, text in flash_files.items() if key != '/main.qml'):
        raise ValueError('最终组合改变引闪/曝光页面')
    for path in result:
        if not path.startswith('/') or '..' in path.split('/') or 'Harness' in path:
            raise ValueError('非法生产资源路径')
    OUT.mkdir(parents=True, exist_ok=True)
    for key, text in result.items():
        path = OUT / 'qml' / key.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline='\n')
    data = formal.common.rcc(result)
    (OUT / 'combined-ui.rcc').write_bytes(data)
    source_paths = [Path(__file__), HERE/'qml/AfSettingsHost.qml', AF/'SettingsPage.qml', AF/'compose_resources.py',
                    REPLAY/'tools/compose_joint_resources.py', resident_tool, RESIDENT/'qml/mainmenu/ResidentLoader.qml']
    checks = ['qrc:/controlscreen/NativeFlashPage.qml', 'qrc:/FormalExposureGate.qml', 'qrc:/controlscreen/ControlScreen.qml',
              'qrc:/mainmenu/MainScreen.qml', 'qrc:/mainmenu/Menu.qml', 'qrc:/settings/SettingsGeneric.qml',
              'qrc:/mainmenu/ResidentLoader.qml', 'qrc:/af-settings/SettingsPage.qml', 'qrc:/af-settings/AfSettingsHost.qml']
    final = {
        'kind': 'x1d-combined-resource-candidate', 'sourceVersion': 'X1D 1.25.0',
        'qml': {key: digest(value.encode()) for key, value in result.items()},
        'flashInputHashes': report['qml'], 'formalSourceHashes': report['sources'],
        'sourceHashes': {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in source_paths},
        'mainSha256': digest(result['/main.qml'].encode()), 'rccSha256': digest(data), 'rccBytes': len(data),
        'componentChecks': checks, 'soleResourceRegistrar': 'root-combined-runtime',
        'residentAppliedLast': True, 'hardwareRequests': 0, 'installed': False, 'targetValidated': False,
    }
    (OUT / 'manifest.json').write_text(json.dumps(final, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return final


if __name__ == '__main__':
    report = build()
    print(json.dumps({key: report[key] for key in ('mainSha256', 'rccSha256', 'rccBytes', 'hardwareRequests', 'installed')}, ensure_ascii=False))
