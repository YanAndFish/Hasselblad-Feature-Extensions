"""原厂 QML/资产宿主夹具；所有原生方法仅记录内存事件。"""
from pathlib import Path
import hashlib,json,os,re,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];CANDIDATE=HERE.parents[1];ROOT=CANDIDATE.parents[2]
sys.path.insert(0,str(CANDIDATE/'fixes/card-format-r1/build/python-qt515'))
sys.path.insert(0,str(HERE));import patch
sys.path.insert(0,str(CANDIDATE/'evaluation/full-pages'))
import measure as memory_fixture
import prepare as assets_fixture
from PyQt5 import sip
from PyQt5.QtCore import QObject,QUrl,pyqtProperty,pyqtSignal,pyqtSlot,Qt,QPointF
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest
from PyQt5.QtQml import QQmlComponent
os.environ.update(QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML_DISABLE_DISK_CACHE='1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def walk(root):
    seen={};pending=[root]
    while pending:
        item=pending.pop()
        if sip.isdeleted(item):continue
        ptr=int(sip.unwrapinstance(item))
        if ptr in seen:continue
        seen[ptr]=item;pending.extend(item.children())
        if hasattr(item,'childItems'):pending.extend(item.childItems())
    return list(seen.values())
def named(root,name):return [v for v in walk(root) if v.objectName()==name]
def wait_for(predicate,label,ms=7000):
    for i in range(max(1,ms//20)):
        if predicate():return
        QTest.qWait(20)
    raise AssertionError('timeout: '+label)
class Native(memory_fixture.NativeMethods):
    def __init__(self):super().__init__();self.actions=[]
    resetGlobalImageSequenceCounterSucceeded=pyqtSignal(str)
    @pyqtSlot(result=bool)
    def isRunningSimulation(self):return True
    @pyqtSlot(str,result=bool)
    def isLatin(self,text):return True
    @pyqtSlot(int,result=str)
    def storageSlotName(self,card):return 'SD'+str(card+1)
    @pyqtSlot()
    def wantToSeeFWUpdateRetryClicked(self):self.actions.append(('secretClick',))
    @pyqtSlot()
    def requestLensFirmwareVersion(self):self.actions.append(('readLensVersion',))
    @pyqtSlot()
    def upgradeNodes(self):self.actions.append(('upgrade',))
    @pyqtSlot(str)
    def saveDbTemplateFromCurrent(self,name):self.actions.append(('saveProfile',name))
    @pyqtSlot()
    def collectLogs(self):self.actions.append(('collectLogs',))
    @pyqtSlot(int)
    def format(self,card):self.actions.append(('format',card))
def native_type(source):
    attrs={}
    for kind,name,value in re.findall(r'property (int|real|bool|string) (\w+):\s*([^;\n]+)',source):
        value=json.loads(value);typ={'int':int,'real':float,'bool':bool,'string':str}[kind]
        signal=pyqtSignal();attrs[name+'Changed']=signal
        def setter(self,v,n=name,default=value):
            self.fixtureWrites.append(n);old=self.fixtureValues.get(n,default);self.fixtureValues[n]=v
            if old!=v:getattr(self,n+'Changed').emit()
        attrs[name]=pyqtProperty(typ,lambda self,n=name,v=value:self.fixtureValues.get(n,v),setter,notify=signal)
    return type('NativeFixture',(Native,),attrs)
def prepare(label='suite',instrument=True):
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    values,factory=patch.resources();full=dict(factory);full.update(values)
    work=HERE/'build/host'/label/'qml';work.mkdir(parents=True,exist_ok=True)
    for name,value in full.items():
        value=re.sub(r'^\.?import com\.hasselblad\..*\n','',value,flags=re.M)
        value=value.replace('qrc:///',work.as_uri()+'/').replace('qrc:/',work.as_uri()+'/')
        if instrument and name in ('/settings/SettingsGeneric.qml','/mainmenu/Menu.qml'):
            model='listModel' if name.endswith('SettingsGeneric.qml') else 'menu_model'
            value=value.replace('    id: root','    id: root\n    property alias testList: list\n    function testRows() {var a=[];for(var i=0;i<'+model+'.count;i++){var r='+model+'.get(i);a.push({name:r.name || r.settingsList,text1:r.text1 || r.label,text2:r.text2});}return JSON.stringify(a)}',1)
        if instrument and name=='/settings/SettingsGeneric.qml':
            value=value.replace('                id: baseItem','                id: baseItem\n                property string testRowKey: name',1)
            value=value.replace('section.delegate:\n            Item {','section.delegate:\n            Item {\n            objectName: "testSection"',1)
        path=work/name.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value,encoding='utf-8')
    sys.path.insert(0,str(ROOT/'x1d/tools'));from binary import ArmElf
    assets=assets_fixture.extract_assets(ArmElf.load('usr/bin/victory-gui'))
    for name,value in assets.items():
        path=work/name.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    # 特殊工具的路由使用显式壳，不能据此宣称原厂工具或其内存已经验收。
    for file in ('components/GreyBalanceTool.qml','settings/DateTime.qml','settings/SpiritLevelView.qml','settings/ProfilesView.qml','components/controls/FavoriteAddSelector.qml'):
        content='''import QtQuick 2.0
Rectangle { objectName: "TransientRouteFixture"; property string upperMenuLabel; property string menuLabel; property var targetModel; property var favoriteModel; property var inputValue; function populateModel(v){inputValue=v} }
'''
        if file.endswith('FavoriteAddSelector.qml'):content=content.replace('objectName:', 'signal subMenuAboutToShow(var menuName); objectName:')
        (work/file).write_text(content,encoding='utf-8')
    # CardFormat/GenericConfirm 均使用真实原厂控件；仅状态栏依赖隔离为无服务 Item。
    (work/'components/StatusRow.qml').write_text('import QtQuick 2.0\nItem {}\n',encoding='utf-8')
    main=(work/'mainmenu/MainScreen.qml').read_text(encoding='utf-8')
    # About fixture API allowlist
    main = re.sub(r'(?m)^\s*suc\.(request\w+)\(\)\s*$', lambda m: m[0] if m[1] == 'requestLensFirmwareVersion' else '', main)
    start=main.index('    Connections {\n        target: (menu_loader.status');end=main.index('            Component.onDestruction: active = false',start)
    block=main[start:main.index('\n    }',end)+len('\n    }')]
    methods=main[main.index('    function closeMenu()'):main.index('    onFocusChanged:')]
    states=main[main.index('    states: ['):main.index('    transitions: [')]
    mocks='GlobalConstants {id:constants}'
    harness='''import QtQuick 2.0
import "@ROOT@/mainmenu"
import "@ROOT@/common"
import "@ROOT@/settings/scripts/MenuItemImporter.js" as MenuItems
import "@ROOT@/scripts/Keys.js" as MKeys
Item {
 id:root;width:640;height:480;focus:true
 signal closeMain()
 property bool acceptKeys:true
 property var favoriteModel:[]
 Item {id:grid;property var model:[]}
 @MOCKS@
 @BLOCK@
 @METHODS@
 @STATES@
 function openMenu(index){root.closeMenu();root.state=["camera_menu","settings_menu","video_menu"][index]}
 function openPage(name){menu_loader.item.activateSubMenu(name,"@ROOT@/settings/SettingsGeneric.qml",name)}
 function openSpecial(name,file){menu_loader.item.activateSubMenu(name,"@ROOT@/"+file,name)}
 function closePage(){menu_loader.item.closeSubMenus()}
 function canOpen(){return menu_loader.item!==null && menu_loader.status===Loader.Ready}
 function selectedMenu(){return menu_loader.item}
 function selectedPage(){if(!menu_loader.item)return null;var loaders=menu_loader.item.children;return null}
 function warmCount(){return menu_loader.readyCount}
 property alias testHost:menu_loader
}'''.replace('@ROOT@',work.as_uri()).replace('@MOCKS@',mocks).replace('@BLOCK@',block).replace('@METHODS@',methods).replace('@STATES@',states)
    path=work/'Harness.qml';path.write_text(harness,encoding='utf-8')
    return work,path
class Fixture:
    def __init__(self,label='suite',instrument=True):
        self.work,path=prepare(label,instrument);self.view=QQuickView();self.keep={};self.warnings=[]
        source=memory_fixture.NATIVE+'''\nproperty int currentState:0
property int system_state:0
property int StateUp:2
property bool preventTopSwipe:false
property int collecting_logs:0
property bool wifiAvailable:true
property string SuSerial:"fixture"
property bool isWedge:true
property bool isCFV:false
property bool hideDemoItems:true
property bool usingUnicodeLanguage:false
property bool showSecretMenuItems:true
property string emptyString:""
property int thumbwheel_mode:0
property string keyMapsName:"KeyMapsWedge.js"
property string menuItemSpecificationsName:"MenuItemSpecificationsWedge.js"
property int capabilities:3
property bool hts_attached:false
property bool cambody_attached:false
property string lensVersion:"fixture"
property bool ram_only_mode:false
property bool card_access:false
'''
        for name in ('Settings','System','Camera','Lens','BodySync','Cambody','Config','ContentModel','GlobalStateInfo','DemoState','Upgrader','prodinfo','guiconfig','suc','cambody','farm'):
            obj=native_type(source)();self.keep[name]=obj;self.view.rootContext().setContextProperty(name,obj)
            if name in ('System','Camera'):self.view.rootContext().setContextProperty(name.lower(),obj)
        config_source=memory_fixture.property_block(memory_fixture.data()['pages'],'configstore',{'focus_size':('int','39322050'),'GUI_idle_timeout':('int','30'),'SYS_standby_idle_timeout':('int','5'),'EVFPreviewTimeout':('int','2'),'CustomOption_FocusPeaking':('bool','true')})
        self.config=native_type(config_source)();self.keep['configstore']=self.config;self.view.rootContext().setContextProperty('configstore',self.config)
        self.view.engine().warnings.connect(lambda es:self.warnings.extend(e.toString() for e in es))
        self.view.setSource(QUrl.fromLocalFile(str(path)))
        assert self.view.status()==QQuickView.Ready,[e.toString() for e in self.view.errors()]
        self.view.show();QTest.qWait(300);self.root=self.view.rootObject()
    def native_update(self,who,name,value):
        obj=self.keep[who];obj.fixtureValues[name]=value;getattr(obj,name+'Changed').emit()
    def start_warm(self):
        self.native_update('System','system_state',2)
        wait_for(lambda:len(self.pages())==23 and all(p.property('residentPrepared') for p in self.pages()),'23 prepared pages',12000)
        wait_for(lambda:len(named(self.root,'specialItem'))==99 and all(p.property('status')==1 for p in named(self.root,'specialItem')),'99 ready rows',7000)
        QTest.qWait(100)
    def pages(self):return named(self.root,'SettingsGeneric_root')
    def page(self,name):return next(p for p in self.pages() if p.property('itemValues')==name)
    def open_menu(self,index):self.root.openMenu(index);wait_for(self.root.canOpen,'menu open');QTest.qWait(250)
    def open_page(self,name):
        self.root.openPage(name);wait_for(lambda:self.page(name).property('residentPresented'),'page open');QTest.qWait(250);return self.page(name)
    def close(self):self.view.setSource(QUrl());QTest.qWait(100)
    def errors(self):return [s for s in self.warnings if 'Implicitly defined onFoo properties in Connections are deprecated' not in s]
