"""原厂 Menu / SettingsGeneric + 原厂子控件的离线组合测试，原生业务接口为显式替身。"""
from pathlib import Path
import json
import re
import sys

from test_resident import HERE, ROOT, source_hashes
from build import baseline, build, transform, PATHS
from PySide6.QtCore import QObject, QUrl, Qt, QPoint, Property, Slot, Signal, qVersion
from PySide6.QtGui import QGuiApplication, QImage, QColor
from PySide6.QtQml import QQmlPropertyMap, QQmlProperty
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest

class CameraMock(QObject):
    changed = Signal()
    def __init__(self):
        super().__init__(); self.point = 0.5; self.writes = 0; self.upgrades = 0
    @Property(float, notify=changed)
    def focus_point(self): return self.point
    @focus_point.setter
    def focus_point(self, value): self.point = value; self.writes += 1; self.changed.emit()
    @Slot(float, result=float)
    def firstComponent(self, value): return 0.5
    @Slot(float, result=float)
    def secondComponent(self, value): return 0.5
    @Slot(float, float, result=float)
    def combine(self, x, y): return x+y
    @Slot()
    def upgradeNodes(self): self.upgrades += 1
    @Slot(str, result='QVariantList')
    def getVariableListModel(self, name): return ['A', 'B'] if name else []
    @Slot(str, 'QVariant', result=str)
    def getUntranslatedDisplayValue(self, name, value): return str(value)
    @Slot(str, 'QVariant', result=str)
    def stringTranslated(self, name, value): return str(value)
    @Slot(str, 'QVariant', result=str)
    def getDisplayValue(self, name, value): return str(value)

MOCKS = '''
    GlobalConstants { id: constants }
    QtObject {
        id: guiconfig; objectName: "guiconfig"
        property bool isWedge: true
        property bool isCFV: false
        property bool hideDemoItems: false
        property bool usingUnicodeLanguage: false
        property string emptyString: ""
        property bool showSecretMenuItems: false
        property int versionClicks: 0
        function isRunningSimulation() { return true }
        function isLatin(value) { return true }
        function wantToSeeFWUpdateRetryClicked() { versionClicks++ }
    }
    QtObject {
        id: configstore; objectName: "configstore"
        property string testValue: "initial"
        property int focus_size: 39322050
        signal focusSizeChanged()
        signal expModeChanged()
    }
    QtObject { id: cambody; signal capabilitiesChanged(); signal hts_attachedChanged() }
    QtObject {
        id: suc; objectName: "suc"; signal cambody_attachedChanged()
        property int lensVersions: 0
        function requestLensFirmwareVersion() { lensVersions++ }
    }
    QtObject { id: farm; signal resetGlobalImageSequenceCounterSucceeded(string newDir) }
    QtObject { id: prodinfo; function isNewH6DisplayQml() { return false } }
'''

ITEMS = '''
var SettingType = {SUBHEADER:0, TEXT:1, TEXTBUTTON:2, BUTTON:3, DROPDOWN:4,
                   CHECKBOX:5, BOOL:6, SLIDER:7, EDITTEXT:8}
function row(type, name, text, proxy) {
    return { editType:type, name:name, text1:text, text2:"", suppressUnitOn:"",
             enableCond:"true", proxy:proxy, demo:false, validCheck:"" }
}
function getSettingsList(name) {
    if(name === "about") return [row(SettingType.TEXTBUTTON,"versionID","Version",System)]
    if(name === "service") return [row(SettingType.BUTTON,"fwUpdateRetry","Retry",System)]
    if(name === "sectioned") return [row(SettingType.SUBHEADER,"","Group",configstore), row(SettingType.TEXT,"testValue","Value",configstore)]
    return [row(SettingType.TEXT,"testValue","Value",configstore)]
}
'''

def prepare():
    build()
    original = baseline()
    work = HERE/'build/original-pages'
    work.mkdir(parents=True, exist_ok=True)
    for key, value in original.items():
        if key in PATHS: value = transform(key, value)
        # 仅主机工作副本适配：业务插件换显式替身，路径换本机，5.x 图形效果由透明替身替代。
        value = re.sub(r'^import com\.hasselblad\..*\n', '', value, flags=re.M)
        value = re.sub(r'^import QtGraphicalEffects.*\n', '', value, flags=re.M)
        value = value.replace('qrc:///', work.as_uri()+'/')
        target = work/key.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8')
    (work/'mainmenu/ResidentLoader.qml').write_text((HERE/'qml/mainmenu/ResidentLoader.qml').read_text(encoding='utf-8'), encoding='utf-8')
    (work/'settings/components/BoundsEffectGradient.qml').write_text('import QtQuick 2.0\nItem { property color fadeColor; visible: false }', encoding='utf-8')
    (work/'settings/scripts/MenuItemImporter.js').write_text(ITEMS, encoding='utf-8')
    (work/'scripts/Keys.js').write_text('''
function pressedFn(name, key) { return name === "ESCAPE" && key === Qt.Key_Escape }
function pressedFnAcc(name, event) { if(pressedFn(name,event.key)) { event.accepted=true; return true } return false }
''', encoding='utf-8')
    main = (work/'mainmenu/MainScreen.qml').read_text(encoding='utf-8')
    # About fixture API allowlist
    main = re.sub(r'(?m)^\s*suc\.(request\w+)\(\)\s*$', lambda m: m[0] if m[1] == 'requestLensFirmwareVersion' else '', main)
    start = main.index('    Connections {\n        target: (menu_loader.status')
    stop = main.index('            Component.onDestruction: active = false', start)
    loader = main[start:main.index('\n    }',stop)+len('\n    }')]
    harness = '''import QtQuick 2.0
import "mainmenu"
import "common"
Item {
    id: root; width: 640; height: 480
    property int closes: 0
    function closeMenu() { menu_loader.active = false; closes++ }
    @MOCKS@
    @LOADER@
    function openMenu(title) {
        menu_loader.itemValues = [{itemText:"Test", settingsList:"plain", itemFile:Qt.resolvedUrl("settings/SettingsGeneric.qml"), demo:false, icon:"", enableCond:""}]
        menu_loader.setSource(Qt.resolvedUrl("mainmenu/Menu.qml"), {"text":title, "anchors.fill":"parent"})
        menu_loader.x = 0
        menu_loader.active = true
    }
    function openPage(group) { menu_loader.item.activateSubMenu(group,Qt.resolvedUrl("settings/SettingsGeneric.qml"),group) }
    function closePage() { menu_loader.item.closeSubMenus() }
    function parameter(value) { configstore.testValue = value }
    function changeFocusSize() { configstore.focusSizeChanged() }
    function changeSecrets(value) { guiconfig.showSecretMenuItems = value }
    function capabilityChange() { cambody.capabilitiesChanged(); cambody.hts_attachedChanged(); suc.cambody_attachedChanged(); configstore.expModeChanged() }
    function openDirect(group, title) {
        menu_loader.subItem = group
        menu_loader.subItemLoader = Qt.resolvedUrl("settings/SettingsGeneric.qml")
        menu_loader.label = group
        menu_loader.scrollToSubmenuItem = "testValue"
        menu_loader.visible = false
        openMenu(title)
    }
}'''.replace('@MOCKS@', MOCKS).replace('@LOADER@',loader)
    (work/'Harness.qml').write_text(harness, encoding='utf-8')
    # 测试占位图只避免缺文件日志，不用于视觉或性能结论。
    (work/'icons').mkdir(exist_ok=True)
    pixel=QImage(2,2,QImage.Format_ARGB32); pixel.fill(QColor('white'))
    for name in ('plain.png','popupButtonArrow.png','exclamationMark.png'):
        pixel.save(str(work/'icons'/name))
    return work

def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    work=prepare()
    view=QQuickView(); warnings=[]
    view.engine().warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    camera=CameraMock()
    maps=[]
    for name, values in {'GlobalStateInfo':{'afSselectedIndex':0}, 'System':{'versionID':'fixture'},
                         'DemoState':{'demoOn':False}}.items():
        m=QQmlPropertyMap(); maps.append(m)
        for key,value in values.items(): m.insert(key,value)
        view.rootContext().setContextProperty(name,m)
    view.rootContext().setContextProperty('Camera',camera)
    view.rootContext().setContextProperty('Upgrader',camera)
    view.rootContext().setContextProperty('Settings',camera)
    # Lens 信号由独立 QObject 提供；未加载任何固件业务插件。
    class LensMock(QObject): lens_familyChanged=Signal()
    lens=LensMock(); view.rootContext().setContextProperty('Lens',lens)
    view.setSource(QUrl.fromLocalFile(str(work/'Harness.qml')))
    assert view.status()==QQuickView.Ready, [e.toString() for e in view.errors()]
    view.show(); QTest.qWait(180)
    root=view.rootObject(); checks=[]
    def find(name, item=None):
        item = root if item is None else item
        if item.objectName() == name: return item
        for child in item.childItems():
            found = find(name, child)
            if found is not None: return found
        return None
    def check(label,condition):
        if not condition:
            print('\n'.join(warnings))
        assert condition,label
        checks.append(label)
    menu=root.findChild(QObject,'Menu_root')
    page=root.findChild(QObject,'SettingsGeneric_root')
    check('原厂两个页面在首次打开前已存在且唯一', menu is not None and page is not None and len(root.findChildren(QObject,'Menu_root'))==len(root.findChildren(QObject,'SettingsGeneric_root'))==1)
    mainhost=root.findChild(QObject,'menu_Loader')
    entry=root.findChild(QObject,'entry_loader')
    menu_list=root.findChild(QObject,'Menu_list')
    settings_list=root.findChild(QObject,'SettingsGeneric_list')
    root.capabilityChange(); root.changeFocusSize(); root.changeSecrets(True); lens.lens_familyChanged.emit(); QTest.qWait(40)
    check('后台事件不填充模型不写焦点不打开弹窗', menu_list.property('count')==settings_list.property('count')==camera.writes==0 and not root.findChild(QObject,'subDialogLoader').property('active'))
    check('预热不触发 About 的读设备动作',root.findChild(QObject,'suc').property('lensVersions')==0)
    root.changeSecrets(False)
    root.openMenu('CAMERA'); QTest.qWait(80)
    check('真实菜单原 onLoaded 填充列表', menu_list.property('count')==1 and menu.property('text')=='CAMERA')
    root.openPage('sectioned'); QTest.qWait(100)
    check('实际通用页打开刷新标签与条目', page.property('itemValues')=='sectioned' and page.property('upperMenuLabel')=='CAMERA' and settings_list.property('count')==1)
    check('实际页输入焦点有效', settings_list.property('activeFocus'))
    root.changeFocusSize(); check('呈现时原焦点修正只执行一次', camera.writes==1)
    root.closePage(); QTest.qWait(50)
    check('关闭清掉选项行但保留页面', settings_list.property('count')==0 and not page.property('visible') and root.findChild(QObject,'SettingsGeneric_root')==page)
    root.changeFocusSize(); check('关闭后焦点修正断开',camera.writes==1)
    root.parameter('changed'); root.openPage('plain'); QTest.qWait(80)
    check('第二次进入复用原对象并重置选择', root.findChild(QObject,'SettingsGeneric_root')==page and page.property('itemValues')=='plain' and settings_list.property('lastIndex')==-1)
    def text_values(item):
        result=[item.property('text')] if item.metaObject().indexOfProperty('text')>=0 else []
        for child in item.childItems(): result.extend(text_values(child))
        return result
    check('显示重新读取的参数值', 'changed' in text_values(settings_list))
    check('分节页转普通页不会残留 section',QQmlProperty(settings_list,'section.property').read()=='')
    check('二次打开焦点回到选项列表', settings_list.property('activeFocus'))
    # 使用实际键盘返回路径，检验 Loader 层级与动态上下文。
    QTest.keyClick(view,Qt.Key_Escape); QTest.qWait(60)
    check('返回键先关子页', not entry.property('active') and mainhost.property('active'))
    QTest.keyClick(view,Qt.Key_Escape); QTest.qWait(60)
    check('第二次返回关主菜单', not mainhost.property('active') and root.property('closes')==1)
    root.openDirect('plain','GENERAL'); QTest.qWait(120)
    check('收藏夹直达解除隐藏且标题正确', mainhost.property('visible') and page.property('visible') and page.property('upperMenuLabel')=='GENERAL')
    check('收藏夹直达滚动请求被消费', entry.property('scrollToSubmenuItem')=='' and settings_list.property('currentIndex')==0)
    root.openPage('generalSettingsAbout'); QTest.qWait(80)
    check('用户打开 About 才执行一次原读动作',root.findChild(QObject,'suc').property('lensVersions')==1)
    root.openPage('about'); QTest.qWait(100)
    check('已打开的同类型页可切换新参数',page.property('itemValues')=='about' and settings_list.property('count')==1)
    version=find('textButtonDelegate')
    check('版本入口仍存在', version is not None)
    version.gotSelected(); check('版本入口保留原回调', root.findChild(QObject,'guiconfig').property('versionClicks')==1)
    root.changeSecrets(True); QTest.qWait(80)
    check('当前页隐藏维护通知仍可出现', root.findChild(QObject,'subDialogLoader').property('active'))
    root.closePage(); root.openPage('service'); QTest.qWait(100)
    button=find('buttonDelegate_menuButton')
    check('Service retry 按钮保留', button is not None)
    button.clicked.emit(); QTest.qWait(100)
    confirm=root.findChild(QObject,'GenericConfirm_root')
    check('Retry 必须先显示原厂确认框', confirm is not None and camera.upgrades==0)
    confirm.rightSelected.emit(); check('确认只执行一次原厂 action', camera.upgrades==1)
    root.closePage(); QTest.qWait(80)
    root.openPage('service'); QTest.qWait(80)
    find('buttonDelegate_menuButton').clicked.emit(); QTest.qWait(80)
    root.findChild(QObject,'GenericConfirm_root').rightSelected.emit()
    check('重复进入无重复升级连接', camera.upgrades==2)
    root.closeMenu(); QTest.qWait(80)
    root.openMenu('TIMERS'); QTest.qWait(50); root.openPage('plain'); QTest.qWait(50)
    inform=root.findChild(QObject,'informDialog')
    inform.setProperty('timeVisible',120); inform.setProperty('visible',True)
    root.closePage(); QTest.qWait(200)
    check('关闭停止临时提示计时器并清标志',not inform.property('visible') and not inform.property('closeDialog'))
    root.openPage('plain'); QTest.qWait(50)
    inform.setProperty('timeVisible',4000); inform.setProperty('visible',True); QTest.qWait(200)
    check('重开不受旧提示计时器影响',inform.property('visible') and not inform.property('closeDialog'))
    root.closePage(); root.openPage('plain'); QTest.qWait(80)
    def drag():
        QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,QPoint(200,250))
        for x in range(220,541,20): QTest.mouseMove(view,QPoint(x,250),8)
        QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,QPoint(540,250)); QTest.qWait(250)
    drag()
    check('原厂右滑先关闭通用设置页',not entry.property('active') and mainhost.property('active'))
    drag()
    check('原厂右滑再关闭主菜单',not mainhost.property('active'))
    check('两个实际页面最终仍为原实例', root.findChild(QObject,'Menu_root')==menu and root.findChild(QObject,'SettingsGeneric_root')==page)
    # Qt6 对原厂旧式 Connections 提示弃用；其他警告一律失败。
    unexpected=[w for w in warnings if 'Implicitly defined onFoo properties in Connections are deprecated' not in w]
    check('无新增 QML 错误',not unexpected)
    report={'passed':True,'hostQt':qVersion(),'checks':checks,'cameraRequests':0,
            'nativePluginsLoaded':False,'targetQt55StillRequired':True,'mockUpgradeActions':camera.upgrades,
            'adaptations':['只移除主机副本原生插件 import','QRC URL 改本机 URL','BoundsEffectGradient 透明替身',
                           'MenuItemImporter 和 Keys 显式测试输入','3 张图标占位图'],
            'qt6DeprecationWarnings':len(warnings)-len(unexpected), 'sourceHashes':source_hashes(),
            'manifest':json.loads((HERE/'build/overlay/manifest.json').read_text(encoding='utf-8'))}
    (HERE/'build/original-pages-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks),'hostQt':qVersion()},ensure_ascii=False))
    view.setSource(QUrl()); QTest.qWait(20)

if __name__=='__main__': run()
