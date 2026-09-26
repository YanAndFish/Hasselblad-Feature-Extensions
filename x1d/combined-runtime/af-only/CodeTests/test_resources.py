"""真实 QML/RCC 的组合与 AF 页面生命周期验证；业务接口均为显式替身。"""
from pathlib import Path
import hashlib
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
from PySide6.QtCore import QObject, QUrl, QResource, QFile, QIODevice, qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent, QQmlPropertyMap
from PySide6.QtTest import QTest
import build as combined


def run():
    report = combined.build()
    checks = []
    def check(label, condition):
        assert condition, label
        checks.append(label)

    original_report = dict(report)
    app = QGuiApplication.instance() or QGuiApplication([])
    rcc = combined.OUT/'combined-ui.rcc'
    check('最终单一生产 RCC 可以注册', QResource.registerResource(str(rcc)))
    for key, expected in report['qml'].items():
        file = QFile(':'+key)
        check('资源逐字回读 '+key, file.open(QIODevice.OpenModeFlag.ReadOnly))
        check('资源摘要 '+key, hashlib.sha256(bytes(file.readAll())).hexdigest() == expected)
        file.close()
    check('仅列出的生产文件入包', not any('Harness' in key for key in report['qml']))
    menu = (combined.OUT/'qml'/combined.AF_MENU.lstrip('/')).read_text(encoding='utf-8')
    check('原厂 AF 与页内设置入口均保留且各一次', menu.count(combined.AF_ANCHOR) == 1 and menu.count(combined.AF_ENTRY) == 1)
    af_section=menu.split('var cameraSettingsAutofocus = [',1)[1].split('var cameraSettingsManualFocus = [',1)[0]
    check('入口位于自动对焦页原厂项目后', af_section.index(combined.AF_ENTRY)>af_section.index('CustomOption_AfLed') and 'editType: SettingType.BUTTON' in af_section)
    check('不增加同级相机菜单项', combined.AF_ENTRY not in menu.split('var cameraMenuItems = [',1)[1])
    generic=(combined.OUT/'qml/settings/SettingsGeneric.qml').read_text(encoding='utf-8')
    check('入口沿用原厂子页加载并接回返回事件','activateSettingsSubMenu("cameraSettingsAdvancedAF", "qrc:///af-settings/AfSettingsHost.qml", "AF 设置")' in generic and 'item.afCloseRequested.connect(subDialog.closeSubDialog)' in generic)
    check('原厂对焦包围入口保留', 'cameraSettingsFocusBracketing' in menu)
    check('原厂物理对焦入口未替换', 'cameraSettingsAutofocus' in menu and 'cameraSettingsManualFocus' in menu)

    engine = QQmlEngine()
    messages = []
    engine.warnings.connect(lambda values: messages.extend(error.toString() for error in values))
    backend = QQmlPropertyMap()
    for key, value in {'command':'', 'connected':True, 'busy':False, 'probe':0, 'fast':0, 'fine':0,
                       'activeProbe':0, 'activeFast':0, 'activeFine':0, 'newDirection':False,
                       'fastAdvanceMs':65534, 'fineAdvanceMs':65534,
                       'fastAdvanceAvailable':False, 'fineAdvanceAvailable':False,
                       'fastPresets':[65535]*4, 'finePresets':[65535]*5,
                       'revision':1, 'statusText':'offline-test'}.items():
        backend.insert(key, value)
    commands = []
    backend.valueChanged.connect(lambda key, value: commands.append(json.loads(value)) if key == 'command' and value else None)
    engine.rootContext().setContextProperty('hblAf', backend)
    component = QQmlComponent(engine, QUrl('qrc:/af-settings/AfSettingsHost.qml'))
    check('真实 AF 导航容器编译', component.isReady() and not component.isError())
    host = component.create()
    check('真实 AF 导航容器创建', host is not None)
    host.setProperty('width',640)
    host.setProperty('height',480)
    returns=[]
    host.afCloseRequested.connect(lambda:returns.append('close'))
    page = host.findChild(QObject,'AfSettingsPage')
    QTest.qWait(250)
    check('构造后未进入不启动查询', page is not None and not page.property('pageActive') and not any(c.get('value') is True for c in commands))
    host.populateModel('cameraSettingsAdvancedAF')
    QTest.qWait(250)
    check('原厂菜单 onLoaded 初始化后进入', page.property('pageActive') and commands[-1] == {'op':'visible','value':True})
    page.backRequested.emit()
    QTest.qWait(250)
    check('页面返回先停查询再交原导航隐藏', not page.property('pageActive') and not host.property('visible') and commands[-1] == {'op':'visible','value':False})
    check('返回事件只发一次给原厂子页面',returns==['close'])
    count = len(commands)
    QTest.qWait(1100)
    check('关闭状态不会恢复后台查询', len(commands) == count)
    host.setProperty('visible',True)
    QTest.qWait(250)
    check('仅重新可见不会自动呈现', not page.property('pageActive'))
    host.populateModel('cameraSettingsAdvancedAF')
    QTest.qWait(250)
    host.setProperty('visible',False)
    QTest.qWait(250)
    check('外层导航关闭同样停止查询', not page.property('pageActive') and commands[-1] == {'op':'visible','value':False})
    host.setProperty('visible',True)
    host.populateModel('cameraSettingsAdvancedAF')
    QTest.qWait(250)
    host.deleteLater()
    QTest.qWait(250)
    check('销毁也关闭页面接口', commands[-1] == {'op':'visible','value':False})
    check('生命周期未提交配置或拍摄操作', all(c.get('op') == 'visible' for c in commands))
    check('真实页面无 QML 错误', not messages)
    component=QQmlComponent(engine,QUrl('qrc:/af-settings/AfQuickEntry.qml'))
    check('参数页快捷入口编译',component.isReady() and not component.isError())
    quick=component.create()
    check('参数页快捷入口创建',quick is not None)
    quick.setProperty('width',640);quick.setProperty('height',480)
    QTest.qWait(250)
    button=quick.findChild(QObject,'AfQuickEntryButton')
    check('快捷按钮位于参数页正中',button.property('x')==264 and button.property('y')==216)
    before=len(commands)
    QTest.qWait(1100)
    check('快捷入口关闭时没有查询',len(commands)==before and not quick.property('pageOpen'))
    quick.openPage();QTest.qWait(350)
    page=quick.findChild(QObject,'AfSettingsPage')
    check('点开快捷入口后呈现真实AF页',quick.property('pageOpen') and page is not None and page.property('pageActive') and commands[-1]=={'op':'visible','value':True})
    page.backRequested.emit();QTest.qWait(350)
    check('返回参数页销毁AF页并停查询',not quick.property('pageOpen') and quick.findChild(QObject,'AfSettingsPage') is None and commands[-1]=={'op':'visible','value':False})
    quick.openPage();QTest.qWait(350);quick.setProperty('available',False);QTest.qWait(350)
    check('参数上下文失效会关闭AF页',not quick.property('pageOpen') and commands[-1]=={'op':'visible','value':False})
    quick.openPage();QTest.qWait(250)
    check('无效上下文拒绝打开',not quick.property('pageOpen'))
    quick.setProperty('available',True);quick.openPage();QTest.qWait(350);quick.setProperty('visible',False);QTest.qWait(350)
    check('离开参数页停查询',not quick.property('pageOpen') and commands[-1]=={'op':'visible','value':False})
    quick.deleteLater();QTest.qWait(250)
    nested=QQmlComponent(engine)
    nested.setData(b'''import QtQuick 2.5
Item {
    id: navigation
    width: 640; height: 480
    property int closeCount: 0
    function openPage() { subDialog.active = true }
    Loader {
        id: subDialog
        anchors.fill: parent
        active: false
        source: "qrc:/af-settings/AfSettingsHost.qml"
        property string itemValues: "cameraSettingsAdvancedAF"
        function closeSubDialog() { active = false; navigation.closeCount += 1 }
        onLoaded: {
            if(item.hasOwnProperty("populateModel") && typeof item.populateModel == 'function')
                item.populateModel(itemValues);
            if(item.hasOwnProperty("afCloseRequested"))
                item.afCloseRequested.connect(subDialog.closeSubDialog);
        }
    }
}''',QUrl('file:///af-original-subdialog-test.qml'))
    check('原厂子页面初始化逻辑编译',nested.isReady() and not nested.isError())
    navigation=nested.create();navigation.openPage();QTest.qWait(350)
    page=navigation.findChild(QObject,'AfSettingsPage')
    check('原厂初始化逻辑进入AF页',page is not None and page.property('pageActive'))
    page.backRequested.emit();QTest.qWait(350)
    check('原厂hasOwnProperty与signal连接确实返回上一级',navigation.property('closeCount')==1 and navigation.findChild(QObject,'AfSettingsPage') is None and commands[-1]=={'op':'visible','value':False})
    navigation.deleteLater();QTest.qWait(250)
    check('两个入口验证未提交配置或拍摄',all(c.get('op')=='visible' for c in commands))
    check('快捷入口生命周期无QML错误',not messages)
    proof = {'passed':True, 'checks':checks, 'qtVersion':qVersion(), 'rccSha256':original_report['rccSha256'],
             'resourceHashes':original_report['qml'], 'sourceHashes':original_report['sourceHashes'],
             'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'hardwareRequests':0, 'installed':False, 'targetQt55Validated':False}
    out = HERE/'CodeTests/output'
    out.mkdir(parents=True,exist_ok=True)
    (out/'resources.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0},ensure_ascii=False))


if __name__ == '__main__':
    run()
