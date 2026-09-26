"""X1D 1.25.0 正式 Qt 适配候选。只离线构建；不访问相机、不覆盖旧包。"""
from pathlib import Path
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / 'build/formal-runtime-ui'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'research'))
import build as common
from prepare_formal_flash_ui import replace_once, read_assets

EXPOSURE = '''                    Camera.startExposing(liveviewAfterExposure)
                    if (!Camera.exposing) {
                        GlobalStateInfo.waitingForExpose = true
                    }
                    mainWindow.item.wasExposingWedge = true
                    if (GlobalStateInfo.evfActive) {
                        mainWindow.item.wasExposingInEvf = true
                    }'''


def build_resources():
    if Path.cwd().resolve() != ROOT:
        raise ValueError('只允许当前 Hasselblad local 内构建')
    raw = (common.BASELINE / 'usr/bin/victory-gui').read_bytes()
    if common.sha(raw) != common.GUI_SHA:
        raise ValueError('GUI 不匹配官方 X1D 1.25.0 固定基线')
    gui = common.ArmElf(raw)
    original = common.qml_files(gui)
    main = original['/main.qml']
    if common.sha(main.encode()) != '9793c2eb01018e1f17610d99934425638884338167fc055237211f70f757e0e3':
        raise ValueError('原厂曝光锚点版本不匹配')
    main = replace_once(main, EXPOSURE, '                    formalExposureGate.begin(liveviewAfterExposure)')
    main = replace_once(main, '                console.log("Got full release")',
                        '                formalExposureGate.cancel()\n                console.log("Got full release")')
    main = replace_once(main, '                console.log("Got half release")',
                        '                formalExposureGate.cancel()\n                console.log("Got half release")')
    main = replace_once(main, '    function stopExposure()\n    {',
                        '    function stopExposure()\n    {\n        formalExposureGate.cancel()')
    additions = (HERE / 'ui/formal-runtime/main_formal_runtime.qml.inc').read_text(encoding='utf-8')
    if additions.count(EXPOSURE) != 1:
        raise ValueError('原厂曝光续行正文必须原样保留')
    main = main[:main.rfind('}')] + additions + '\n}\n'
    control = original['/controlscreen/ControlScreen.qml']
    control = replace_once(control, '    id: scope', '    id: scope\n    clip: true')
    control = replace_once(control, 'property bool preventSwipe: popupOpen || Camera.inSession',
                           'property bool preventSwipe: popupOpen || Camera.inSession || formalFlashSwipe.secondPage || formalFlashSwipe.drag.active')
    control = replace_once(control, '        objectName: "ControlScreen_root"',
                           '        objectName: "ControlScreen_root"\n        parent: formalFlashTrack')
    swipe = (HERE / 'ui/formal/ControlSwipe.qml.inc').read_text(encoding='utf-8')
    swipe = replace_once(swipe, '            FlashPage {', '            NativeFlashPage {')
    control = control[:control.rfind('}')] + swipe + '\n}\n'
    edited = {'/main.qml': main, '/controlscreen/ControlScreen.qml': control}
    for name in ('FlashPage.qml', 'FlashIconButton.qml', 'FlashText.qml', 'FlashValueText.qml', 'FlashLampIcon.qml', 'FlashStyle.qml', 'FlashToggleRow.qml'):
        edited['/controlscreen/' + name] = (HERE / 'ui/formal' / name).read_text(encoding='utf-8')
    # 定稿视觉不变：仅增协议能力门控，让未实现组/造型灯保持可见且不能假装可用。
    page = edited['/controlscreen/FlashPage.qml']
    page = replace_once(page, '    property bool canTest: false',
                        '    property int supportedGroupCount: 16\n    property bool modelingLampAvailable: false\n    property bool canTest: false')
    page = replace_once(page, '        if (index < 0 || index >= groups.count || Math.floor(index)!==index ||',
                        '        if (index < 0 || index >= supportedGroupCount || Math.floor(index)!==index ||')
    page = replace_once(page, '    function toggleLamp(index) {',
                        '    function toggleLamp(index) {\n        if (!modelingLampAvailable || index>=supportedGroupCount) return false')
    page = replace_once(page, '    function toggleVisibleGroup(index) {',
                        '    function toggleVisibleGroup(index) {\n        if (index>=supportedGroupCount) return false')
    page = replace_once(page, '                        opacity: selected ? 1 : 0.45',
                        '                        opacity: index>=page.supportedGroupCount ? 0.18 : selected ? 1 : 0.45')
    page = replace_once(page, 'objectName: "FlashSelectGroup"+letter; anchors.fill: parent;',
                        'objectName: "FlashSelectGroup"+letter; anchors.fill: parent; enabled: index<page.supportedGroupCount;')
    page = replace_once(page, 'objectName: "FlashLamp"+groupRow.groupValue.letter; anchors.fill: parent;',
                        'objectName: "FlashLamp"+groupRow.groupValue.letter; anchors.fill: parent; enabled: page.modelingLampAvailable;')
    page = replace_once(page, '                    FlashLampIcon { anchors.centerIn: parent;',
                        '                    FlashLampIcon { opacity: page.modelingLampAvailable ? 1 : 0.3; anchors.centerIn: parent;')
    edited['/controlscreen/FlashPage.qml'] = page
    edited['/controlscreen/NativeFlashPage.qml'] = (HERE / 'ui/formal-runtime/NativeFlashPage.qml').read_text(encoding='utf-8')
    edited['/FormalExposureGate.qml'] = (HERE / 'ui/formal-runtime/FormalExposureGate.qml').read_text(encoding='utf-8')
    runtime_components = ['/controlscreen/NativeFlashPage.qml', '/FormalExposureGate.qml', '/controlscreen/ControlScreen.qml']
    if any(not edited.get(path) for path in runtime_components):
        raise ValueError('安装前必须覆盖并提供全部运行时编译验收组件')
    for name, content in edited.items():
        target = OUT / 'qml' / name.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='\n')
    bundle = common.rcc(edited)
    (OUT / 'formal-ui.rcc').write_bytes(bundle)
    for name, data in read_assets(gui).items():
        target = OUT / 'baseline-assets' / Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    sources = list((HERE / 'ui/formal').glob('*')) + list((HERE / 'ui/formal-runtime').glob('*'))
    sources += [Path(__file__), HERE/'native/formal_runtime.cpp', HERE/'native/formal_bridge.h', HERE/'native/formal_install_hold.h']
    report = {
        'kind': 'formal-runtime-ui-offline-candidate', 'sourceVersion': 'X1D 1.25.0',
        'guiSha256': common.GUI_SHA, 'originalMainSha256': common.sha(original['/main.qml'].encode()),
        'qml': {name: common.sha(content.encode()) for name, content in edited.items()},
        'sources': {str(p.relative_to(HERE)).replace('\\','/'): common.sha(p.read_bytes()) for p in sorted(sources) if p.is_file()},
        'rccSha256': common.sha(bundle), 'rccVersion': 1,
        'heartbeatMs': 500, 'disconnectMs': 2000, 'qmlFlushTimeoutMs': 6500,
        'shutterContinuation': 'full-press-after-factory-checks-successful-worker-ack-only',
        'cancelOn': ['full-release','half-release','context-change','mode-change','parameter-change','timeout','native-disconnect','component-destruction'],
        'powerEdits': 'every-draft-change-to-native-worker-gates-and-coalesces',
        'capabilities': {'groups': list('ABCDEF0123456789'), 'modelingLamp': True, 'manualTestFlash': True},
        'uiSettingsIndependent': True, 'masterAcknowledgementRequired': True,
        'exposureParameter': 'mechanical-nominal-TV-third-stop-table-125-to-2000-not-measured-exposure',
        'esDeadlineSource': 'worker-must-use-current-FARM-GFS3-exposure-not-QML-estimate',
        'installed': False, 'hardwareRequests': 0, 'radioRequests': 0,
        'targetRuntimeValidated': False,
        'targetRuntimeComponentCompileChecks': ['qrc:'+path for path in runtime_components],
        'targetRuntimeSuccessMarkerRequires': 'root-object-and-all-three-components-ready-without-create',
    }
    (OUT/'candidate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def compile_runtime():
    report = build_resources()
    include = OUT/'include/QtCore'
    include.mkdir(parents=True, exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n')
    (include/'qfeatures.h').write_text('/* Qt 5.5.1 public ABI. */\n')
    env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(OUT/'global-cache'), ZIG_LOCAL_CACHE_DIR=str(OUT/'local-cache'), PYTHONDONTWRITEBYTECODE='1')
    qt = common.CACHE/'qt-public'
    base = qt/'qtbase-opensource-src-5.5.1'
    declarative = qt/'qtdeclarative-opensource-src-5.5.1'
    flags = ['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
             '-I',str(OUT/'include'),'-isystem',str(base/'include'),'-isystem',str(declarative/'include'),
             '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra']
    obj = OUT/'formal_runtime.o'
    subprocess.run([str(common.COMPILER),'c++','-std=c++11']+flags+['-c',str(HERE/'native/formal_runtime.cpp'),'-o',str(obj)], env=env, check=True)
    layout = OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    libs = [common.BASELINE/('usr/lib/libQt5'+module+'.so.5.5.1') for module in ['Qml','Core']]
    libs += [common.BASELINE/'usr/lib/libstdc++.so.6.0.21', common.BASELINE/'lib/libgcc_s.so.1',
             common.BASELINE/'lib/libdl-2.22.so',common.BASELINE/'lib/libc-2.22.so']
    output = OUT/'libhbl-formal.so'
    subprocess.run([str(common.COMPILER),'cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-shared',
                    '-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),'-Wl,-soname,libhbl-formal.so',str(obj)]+[str(p) for p in libs]+['-o',str(output)], env=env, check=True)
    elf = common.ArmElf(output.read_bytes())
    rel = elf.elf.get_section_by_name('.rel.dyn'); plt = elf.elf.get_section_by_name('.rel.plt')
    if rel['sh_addr']+rel['sh_size'] != plt['sh_addr']:
        raise ValueError('目标 glibc 2.22 重定位表必须连续')
    report['runtimeSha256'] = common.sha(output.read_bytes())
    report['runtimeBytes'] = output.stat().st_size
    report['compiledAbi'] = 'ARM32 hard-float Qt 5.5.1 glibc 2.22'
    report['relocationTablesContiguous'] = True
    report['needed'] = [tag.needed for tag in elf.elf.get_section_by_name('.dynamic').iter_tags() if tag.entry.d_tag=='DT_NEEDED']
    (OUT/'compiled.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__=='__main__':
    result=compile_runtime()
    print(json.dumps({'built':True,'qmlFiles':len(result['qml']),'runtimeBytes':result['runtimeBytes'],'installed':False,'hardwareRequests':0},ensure_ascii=False))
