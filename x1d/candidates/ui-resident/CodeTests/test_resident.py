"""离线 Qt Quick 生命周期测试：真实常驻容器 + 显式页面替身，无相机对象。"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'tools'))
sys.path.insert(0, str(ROOT / 'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
from PySide6.QtCore import QObject, QUrl, Qt, QPoint, qVersion, QResource, QFile, QIODevice
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
from build import baseline, build, transform, compose, PATHS

SHELL = '''import QtQuick 2.0
Rectangle {
    id: page; objectName: "safePage"; color: "black"
    property bool residentPresented: true
    property var residentHost: null
    property string text: ""
    property int snapshot: -1
    property int opens: 0
    property int clicks: 0
    property int received: 0
    property int identity: 0
    Component.onCompleted: { identity = ++harness.created }
    Component.onDestruction: harness.destroyed++
    function residentActivate() { residentDeactivate(); residentPresented = true; opens++ }
    function residentDeactivate() { residentPresented = false; focus = false }
    function populateModel(value) { snapshot = value }
    Connections { target: page.residentPresented ? harness : null; function onPulse() { page.received++ } }
    MouseArea { anchors.fill: parent; onClicked: page.clicks++ }
    Keys.onPressed: { page.clicks++; event.accepted = true }
}
'''
HARNESS = '''import QtQuick 2.0
Item {
    id: harness; width: 640; height: 480
    property int created: 0
    property int destroyed: 0
    property int lazyCreated: 0
    property int lazyDestroyed: 0
    property int loads: 0
    property int parameter: 0
    signal pulse()
    ResidentLoader {
        id: container; objectName: "container"; anchors.fill: parent
        residentSource: Qt.resolvedUrl("Shell.qml")
        focus: active
        onLoaded: { harness.loads++; if (item.populateModel) item.populateModel(harness.parameter); item.forceActiveFocus() }
    }
    function openSafe(value, title) { parameter = value; container.setSource(Qt.resolvedUrl("Shell.qml"), {"text":title}); container.active = true }
    function openLazy() { container.setSource(Qt.resolvedUrl("Lazy.qml"), {}); container.active = true }
    function closePage() { container.active = false }
    function race() { openSafe(10,"discard"); closePage(); openLazy(); closePage(); openSafe(91,"last"); }
    function closeDuringLoad() { openLazy(); closePage(); }
}
'''

def source_hashes():
    files = [*HERE.glob('tools/*.py'), *HERE.glob('CodeTests/*.py'), *HERE.glob('qml/**/*.qml')]
    return {p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def run():
    manifest = build()
    source = baseline()
    checks = []
    def check(label, condition):
        assert condition, label
        checks.append(label)
    for path in PATHS:
        updated = transform(path, source[path])
        marker = '\n// independent-flash-overlay-sentinel\n'
        check('可组合且保留非冲突修改 '+path,
              transform(path, source[path]+marker) == updated+marker)
        try:
            transform(path, updated)
            raise AssertionError('重复应用应拒绝')
        except ValueError:
            check('拒绝重复应用 '+path, True)
    check('仅四个输出资源', set(manifest['resources']) == set(PATHS) | {'/mainmenu/ResidentLoader.qml'})
    independent = '\n    Connections { target: independentSignals; onOtherSignal: {} }\n'
    inputs = {'/main.qml':'latest-flash-and-af-main-sentinel', '/other.qml':'other',
              PATHS[2]:source[PATHS[2]]+independent}
    combined = compose(inputs)
    check('组合保留最新版 main.qml 和其他资源',combined['/main.qml']==inputs['/main.qml'] and combined['/other.qml']=='other')
    check('组合不修改其他候选的连接',combined[PATHS[2]].endswith(independent))
    check('组合不写回输入字典',inputs[PATHS[2]]==source[PATHS[2]]+independent)
    for bad in [source[PATHS[1]].replace('id: entry_loader','id: renamed_loader'),
                source[PATHS[1]]+'\nConnections { target: cambody\n onCapabilitiesChanged: {} }']:
        try:
            transform(PATHS[1],bad)
            raise AssertionError('冲突必须拒绝')
        except ValueError: pass
    check('拒绝缺失和重复的组合锚点',True)
    bundle = HERE/'build/overlay/ui-resident.rcc'
    check('覆盖包固定 RCC v1',bundle.read_bytes()[:8]==b'qres\0\0\0\1')
    check('Qt 可以注册覆盖包',QResource.registerResource(str(bundle),'/resident-test'))
    for key in manifest['resources']:
        f=QFile(':/resident-test'+key)
        assert f.open(QIODevice.ReadOnly)
        data=bytes(f.readAll()); f.close(); del f
        check('QRC 解压后与输出文本完全一致 '+key,
              hashlib.sha256(data).hexdigest()==manifest['resources'][key]['outputSha256'])
    check('测试资源已卸载',QResource.unregisterResource(str(bundle),'/resident-test'))
    generic = transform(PATHS[2], source[PATHS[2]])
    for begin, end in [('case "fwUpdateRetry":', 'case "cardFormatCard0":'),
                       ('case "versionID":', 'default:')]:
        def block(text):
            a = text.index(begin)
            return text[a:text.index(end, a)]
        check('维护入口逐字保留 '+begin, block(generic) == block(source[PATHS[2]]))
    check('升级确认动作保留', 'onRightSelected: Upgrader.upgradeNodes()' in generic)
    check('Qt55 连接门控不用 Qt57 属性', 'Connections {\n        enabled:' not in generic)
    protected = {k: hashlib.sha256(v.encode()).hexdigest() for k,v in source.items()
                 if k not in PATHS}
    check('错误与恢复资源全部排除', all(k not in manifest['resources'] for k in protected))
    work = HERE/'build/host-tests'
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE/'qml/mainmenu/ResidentLoader.qml', work/'ResidentLoader.qml')
    (work/'Shell.qml').write_text(SHELL, encoding='utf-8')
    (work/'Harness.qml').write_text(HARNESS, encoding='utf-8')
    (work/'Lazy.qml').write_text('''import QtQuick 2.0
Rectangle { objectName: "lazyPage"; color: "blue"
 Component.onCompleted: harness.lazyCreated++
 Component.onDestruction: harness.lazyDestroyed++
}''', encoding='utf-8')
    app = QGuiApplication.instance() or QGuiApplication([])
    view = QQuickView()
    warnings = []
    view.engine().warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    view.setSource(QUrl.fromLocalFile(str(work/'Harness.qml')))
    assert view.status() == QQuickView.Ready, [e.toString() for e in view.errors()]
    view.rootObject().openSafe(-1, 'cancelled-before-prewarm-complete')
    view.rootObject().closePage()
    view.show(); QTest.qWait(100)
    root = view.rootObject()
    host = root.findChild(QObject, 'container')
    page = root.findChild(QObject, 'safePage')
    check('首次打开前已构造真实实例', page is not None and root.property('created') == 1)
    identity = page.property('identity')
    check('预热无呈现回调或危险页构造', root.property('loads') == root.property('lazyCreated') == 0)
    check('预热期间打开又关闭不会稍后弹回',not host.property('active') and root.property('loads')==0)
    check('关闭不可见不接输入', not page.property('visible') and not page.property('enabled') and not page.property('activeFocus'))
    root.pulse.emit(); check('关闭不订阅业务信号', page.property('received') == 0)
    root.openSafe(12, 'first'); QTest.qWait(50)
    check('打开刷新参数标题', page.property('snapshot') == 12 and page.property('text') == 'first')
    check('打开获得输入焦点', page.property('visible') and page.property('enabled') and page.property('activeFocus'))
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(200,200))
    QTest.keyClick(view, Qt.Key_Space)
    check('点击按键每次只响应一次', page.property('clicks') == 2)
    for i in range(20):
        root.closePage(); root.pulse.emit()
        check('关闭保留对象 '+str(i), page.property('identity') == identity and root.property('destroyed') == 0)
        root.openSafe(i, 'round'+str(i)); QTest.qWait(20)
        root.pulse.emit()
    check('反复开关没有重复连接', page.property('received') == 20)
    check('每次打开使用最新参数', page.property('snapshot') == 19 and page.property('text') == 'round19')
    root.openLazy(); QTest.qWait(80)
    check('非白名单只在用户打开时构造', root.property('lazyCreated') == 1 and not page.property('visible'))
    root.closePage(); QTest.qWait(20)
    check('非白名单按旧生命周期销毁', root.property('lazyDestroyed') == 1)
    root.race(); QTest.qWait(70)
    check('同帧竞争只呈现最后请求', page.property('snapshot') == 91 and page.property('text') == 'last' and root.property('lazyCreated') == 1)
    root.closeDuringLoad(); QTest.qWait(50)
    check('关闭取消未开始的异步请求', not host.property('active') and root.property('lazyCreated') == 1)
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(200,200))
    QTest.keyClick(view, Qt.Key_Space)
    check('关闭后的鼠标键盘不落入常驻页', page.property('clicks') == 2)
    check('无 QML 运行警告', not warnings)
    report = {'passed':True, 'hostQt':qVersion(), 'targetQt55StillRequired':True,
              'cameraRequests':0, 'installed':False, 'checks':checks,
              'protectedResourceHashes':protected, 'manifest':manifest, 'sourceHashes':source_hashes()}
    (HERE/'build/validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed':True, 'checks':len(checks), 'hostQt':qVersion()}, ensure_ascii=False))
    view.setSource(QUrl()); QTest.qWait(20)

if __name__ == '__main__':
    run()
