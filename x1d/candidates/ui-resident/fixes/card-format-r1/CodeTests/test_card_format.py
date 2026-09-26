"""原厂与固定 a8 的格式化弹窗离线对照：存储对象为内存替身，零硬件/卡内容。"""
from pathlib import Path
import hashlib,json,os,re,sys
sys.dont_write_bytecode=True
FIX=Path(__file__).resolve().parents[1]
CANDIDATE=FIX.parents[1]
ROOT=CANDIDATE.parents[2]
if '--qt6-diagnostic' not in sys.argv:
    if '--qt515' in sys.argv:sys.argv.remove('--qt515')
    sys.path.insert(0,str(FIX/'build/python-qt515'))
    from PyQt5 import QtCore,QtGui,QtQml,QtQuick,QtTest
    QtCore.Property=QtCore.pyqtProperty;QtCore.Slot=QtCore.pyqtSlot;QtCore.Signal=QtCore.pyqtSignal
    for name,module in {'QtCore':QtCore,'QtGui':QtGui,'QtQml':QtQml,'QtQuick':QtQuick,'QtTest':QtTest}.items():sys.modules['PySide6.'+name]=module
sys.path.insert(0,str(CANDIDATE/'CodeTests'))
import test_original_pages as legacy
from PySide6.QtCore import QObject,QUrl,Qt,Property,Signal,Slot,QPoint,qVersion
from PySide6.QtQml import QQmlPropertyMap,QQmlComponent
from PySide6.QtQuick import QQuickView
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

class StorageMock(QObject):
    changed=Signal()
    def __init__(self):
        super().__init__(); self.card0=1; self.card1=1; self.calls=[]
    @Property(int,constant=True)
    def STORAGE_ABSENT(self):return 0
    @Property(int,notify=changed)
    def card0Status(self):return self.card0
    @Property(int,notify=changed)
    def card1Status(self):return self.card1
    @Property(bool,notify=changed)
    def isFormatting(self):return False
    @Slot(int)
    def format(self,card):self.calls.append(card)  # 仅内存记录；无设备/文件操作。

def visual(item,name):
    if item.objectName()==name:return item
    for child in item.childItems():
        found=visual(child,name)
        if found is not None:return found
    return None

def prepare(mode,factory):
    full=dict(factory)
    fixed=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57/overlay'
    if mode!='factory':
        for p in fixed.rglob('*.qml'):full['/'+p.relative_to(fixed).as_posix()]=p.read_text(encoding='utf-8')
        if mode=='fixed':
            sys.path.insert(0,str(FIX));import patch
            full['/settings/SettingsGeneric.qml']=patch.apply(full['/settings/SettingsGeneric.qml'])
    out=FIX/'build'/mode
    legacy.HERE=out;legacy.build=lambda:None;legacy.baseline=lambda:full;legacy.transform=lambda k,v:v
    dest=out/'qml/mainmenu/ResidentLoader.qml';dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes((fixed/'mainmenu/ResidentLoader.qml').read_bytes())
    work=legacy.prepare()
    page=work/'settings/SettingsGeneric.qml'
    instrumented=page.read_text(encoding='utf-8').replace('    id: root','''    id: root
    function diagnosticRows() {
        var rows=[]; for(var i=0;i<listModel.count;i++) {var row=listModel.get(i);rows.push({name:row.name,text2Type:typeof row.text2,text2:row.text2})}
        return JSON.stringify(rows)
    }''',1).replace('property bool fwRetryPressed : false','property string diagnosticText2Type: typeof text2\n                        property bool fwRetryPressed : false')
    page.write_text(instrumented,encoding='utf-8')
    spec=factory['/settings/scripts/MenuItemSpecificationsWedge.js']
    source=re.search(r'var SettingType = \{.*?\n\};',spec,re.S).group(0)+'\n'
    source+=re.search(r'var generalSettingsStorage = \[.*?\n        \]',spec,re.S).group(0)+'\n'
    source+=re.search(r'var generalSettingsLanguage = \[.*?\n        \]',spec,re.S).group(0)+'\n'
    source+='''function getSettingsList(name) {
        if(name==="storage") return generalSettingsStorage;
        if(name==="language") return generalSettingsLanguage;
        return [{editType:SettingType.TEXT,name:"testValue",text1:"Value",proxy:configstore}];
    }'''
    (work/'settings/scripts/MenuItemImporter.js').write_text(source,encoding='utf-8')
    (work/'scripts/Keys.js').write_text(factory['/scripts/Keys.js'],encoding='utf-8')
    harness=(work/'Harness.qml').read_text(encoding='utf-8')
    harness=harness.replace('property bool isWedge: true','''property bool isWedge: true
        property string keyMapsName: "KeyMapsWedge.js"
        function storageSlotName(card) { return "SD"+(card+1) }''')
    harness=harness.replace('id: farm; signal','id: farm; property bool card_access:false; signal')
    harness=harness.replace('property string testValue: "initial"','property string testValue: "initial"; property int primary_volume_image_raw:0; property int storage_mode:0; property int languageIndex:0')
    (work/'Harness.qml').write_text(harness,encoding='utf-8')
    (work/'components/StatusRow.qml').write_text('import QtQuick 2.0\nItem {}\n',encoding='utf-8')
    return work

def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    factory=legacy.baseline();results=[];checks=[]
    mode=sys.argv[1] if len(sys.argv)>1 else 'fixed'
    scenario=sys.argv[2] if len(sys.argv)>2 else 'languagefirst'
    present=sys.argv[3] if len(sys.argv)>3 else 'both'
    def check(name,condition):
        assert condition,name
        checks.append(name)
    for mode in [mode]:
        work=prepare(mode,factory);view=QQuickView();warnings=[];keep=[]
        view.engine().warnings.connect(lambda es:warnings.extend(e.toString() for e in es))
        camera=legacy.CameraMock();store=StorageMock()
        if present=='card0':store.card1=0
        if present=='card1':store.card0=0
        for name,values in {'GlobalStateInfo':{'afSselectedIndex':0},'System':{'versionID':'fixture'},'DemoState':{'demoOn':False},'Config':{'CardNone':-1,'Card0':0,'Card1':1,'CardRam':2}}.items():
            m=QQmlPropertyMap();keep.append(m)
            for k,v in values.items():m.insert(k,v)
            view.rootContext().setContextProperty(name,m)
        for name,obj in {'Camera':camera,'Settings':camera,'Upgrader':camera,'ContentModel':store}.items():view.rootContext().setContextProperty(name,obj)
        # 参数显示用纯 QML 替身，避免 PySide 把销毁过程的 undefined 转成 Python QVariant。
        sc=QQmlComponent(view.engine());sc.setData(b'''import QtQuick 2.0
QtObject {
 function getDisplayValue(n,v) {return String(v)}
 function getUntranslatedDisplayValue(n,v) {return String(v)}
 function stringTranslated(n,v) {return String(v)}
 function getVariableListModel(n) {return ["A","B"]}
}''',QUrl())
        settings=sc.create();assert settings is not None
        view.rootContext().setContextProperty('Settings',settings)
        class Lens(QObject):lens_familyChanged=Signal()
        lens=Lens();view.rootContext().setContextProperty('Lens',lens)
        view.setSource(QUrl.fromLocalFile(str(work/'Harness.qml')))
        assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
        view.show();QTest.qWait(180);root=view.rootObject()
        if scenario in ('plainfirst','languagefirst'):
            root.openMenu('GENERAL');QTest.qWait(80);root.openPage('language' if scenario=='languagefirst' else 'plain');QTest.qWait(150);root.closePage();QTest.qWait(100)
        initial_page=root.findChild(QObject,'SettingsGeneric_root')
        for cycle in range(2):
            root.openMenu('GENERAL');QTest.qWait(80);root.openPage('storage');QTest.qWait(400)
            page=root.findChild(QObject,'SettingsGeneric_root');sl=root.findChild(QObject,'SettingsGeneric_list')
            if cycle==0:initial_page=page
            for card in ([0] if present=='card0' else [1] if present=='card1' else [0,1]):
                buttons=[]
                def collect(item):
                    if item.objectName()=='buttonDelegate_menuButton':buttons.append(item)
                    for child in item.childItems():collect(child)
                collect(sl)
                assert len(buttons)==2
                # 用真实列表按钮的指针输入进入，确认键仅由 QtTest 派发到离线窗口。
                button=buttons[card];point=button.mapToScene(QPoint(int(button.width()/2),int(button.height()/2)))
                role_type=button.parentItem().property('diagnosticText2Type')
                check('enabled button '+str((cycle,card)),bool(button.property('isEnabled')))
                QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,QPoint(round(point.x()),round(point.y())));QTest.qWait(400)
                dialog=root.findChild(QObject,'CardFormat_root');sub=root.findChild(QObject,'subDialogLoader')
                row={'mode':mode,'cycle':cycle,'card':card,'dialogExists':dialog is not None,'subActive':sub.property('active'),
                     'focusItem':view.activeFocusItem().objectName() if view.activeFocusItem() else None,'listFocus':sl.property('activeFocus'),'text2Type':role_type}
                broken=mode=='a8' and scenario!='storagefirst'
                check('expected entry result '+str((cycle,card)),(dialog is None and not sub.property('active') and role_type=='undefined') if broken else (dialog is not None and sub.property('active') and role_type=='string'))
                if dialog is not None:
                    row.update(state=dialog.property('state'),cardActual=dialog.property('actualCardToFormat'),visible=dialog.property('visible'),enabled=dialog.property('enabled'),focus=dialog.property('activeFocus'),size=[dialog.width(),dialog.height()],position=[dialog.x(),dialog.y()],warning=dialog.property('subText'))
                    QTest.keyClick(view,Qt.Key_F2);QTest.qWait(100)
                    row['cancelClosed']=not sub.property('active')
                    check('correct visible card and preserved warning '+str((cycle,card)),row['cardActual']==card and row['state']=='FormatCard' and row['visible'] and row['enabled'] and row['focus'] and row['size']==[640.0,480.0] and row['warning']=='All content will be erased!')
                    check('cancel returns to list '+str((cycle,card)),row['cancelClosed'] and sl.property('activeFocus'))
                results.append(row);print(json.dumps(row),flush=True)
                if sub.property('active'):sub.closeSubDialog();QTest.qWait(100)
            QTest.keyClick(view,Qt.Key_Escape);QTest.qWait(100)
            QTest.keyClick(view,Qt.Key_Escape);QTest.qWait(100)
            if mode!='factory':check('resident identity after hidden cycle '+str(cycle),root.findChild(QObject,'SettingsGeneric_root')==initial_page and not initial_page.property('residentPresented'))
        unexpected=[v for v in warnings if 'Implicitly defined onFoo properties in Connections are deprecated' not in v]
        check('entry/cancel never calls storage mock',not store.calls)
        if mode=='a8' and scenario!='storagefirst':
            check('negative case only expected text2 exceptions',len(unexpected)==len(results) and all('ReferenceError: text2 is not defined' in w for w in unexpected))
        else:check('no unexpected QML error',not unexpected)
        view.setSource(QUrl());QTest.qWait(40)
    report={'passed':True,'checks':checks,'hostQt':qVersion(),'hardwareRequests':0,'storageAccess':0,'mockFormatCalls':0,'rows':results,'warnings':unexpected,
            'mode':mode,'scenario':scenario,'present':present,'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'patchSha256':hashlib.sha256((FIX/'patch.py').read_bytes()).hexdigest(),
            'purpose':'factory versus installed a8 and one-expression fix; actual Language/Storage lists; pointer entry and key cancel only'}
    reportname='reproduction-'+mode+'-'+scenario+'-'+present+'.json'
    (FIX/'build'/reportname).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'mode':mode,'scenario':scenario,'present':present,'checks':len(checks),'hostQt':qVersion(),'mockFormatCalls':0}))
if __name__=='__main__':run()
