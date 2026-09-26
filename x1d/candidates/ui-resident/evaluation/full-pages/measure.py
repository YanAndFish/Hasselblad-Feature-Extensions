"""独立 Qt5.15/64 位宿主的真实 QML 实例与进程内存差分；不是相机值。"""
from pathlib import Path
import collections,ctypes,gc,hashlib,json,os,re,statistics,sys,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CANDIDATE=HERE.parents[1];OUT=HERE/'build'
sys.path.insert(0,str(CANDIDATE/'fixes/card-format-r1/build/python-qt515'))
os.environ.update(QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML_DISABLE_DISK_CACHE='1')
from PyQt5 import sip
from PyQt5.QtCore import QObject,QUrl,QEvent,qVersion,pyqtProperty,pyqtSignal,pyqtSlot
from PyQt5.QtGui import QGuiApplication,QFontDatabase
from PyQt5.QtQml import QQmlComponent
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest

class Counters(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
def memory():
    dll=ctypes.WinDLL('kernel32',use_last_error=True);dll.GetCurrentProcess.restype=ctypes.c_void_p
    ps=ctypes.WinDLL('psapi',use_last_error=True);ps.GetProcessMemoryInfo.argtypes=(ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong)
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not ps.GetProcessMemoryInfo(dll.GetCurrentProcess(),ctypes.byref(counters),counters.cb):raise ctypes.WinError(ctypes.get_last_error())
    return {'workingSet':counters.WorkingSetSize,'privateCommit':counters.PrivateUsage,'peakWorkingSet':counters.PeakWorkingSetSize}
def settled():
    QTest.qWait(400);samples=[]
    for i in range(5):samples.append(memory());QTest.qWait(100)
    return {'median':{k:int(statistics.median(v[k] for v in samples)) for k in samples[0]},'samples':samples}
def data():return json.loads((OUT/'catalog.json').read_text(encoding='utf-8'))
def property_block(rows,proxy,extras):
    names={r['name']:r['editType'] for p in rows for r in p['rows'] if r.get('proxy')==proxy}
    names.update(extras)
    fields=[]
    for name,t in sorted(names.items()):
        if isinstance(t,tuple):kind,value=t
        else:kind,value=('bool','false') if t in (2,4) else ('int','0')
        fields.append('property '+kind+' '+name+': '+value)
    return '\n'.join(fields)
def mocks(catalog):
    rows=catalog['pages']
    config=property_block(rows,'configstore',{'focus_size':('int','39322050'),'GUI_idle_timeout':('int','30'),'SYS_standby_idle_timeout':('int','5'),'EVFPreviewTimeout':('int','2'),'CustomOption_FocusPeaking':('bool','true')})
    return '''
GlobalConstants {id:constants}
QtObject { id:audit; property int mockReads:0; property int mockActions:0 }
QtObject {id:guiconfig;
 property bool isWedge:true; property bool isCFV:false; property bool hideDemoItems:true; property bool usingUnicodeLanguage:false
 property bool showSecretMenuItems:true; property string emptyString:""; property int thumbwheel_mode:0; property string keyMapsName:"KeyMapsWedge.js"
 function isRunningSimulation(){return true} function isLatin(s){return true}
 function wantToSeeFWUpdateRetryClicked(){audit.mockActions++}
 function storageSlotName(n){return "SD"+(n+1)}
}
QtObject {id:cambody;property int capabilities:3;property bool hts_attached:false}
QtObject {id:suc;property bool cambody_attached:false;property string lensVersion:"fixture"
 function requestLensFirmwareVersion(){audit.mockReads++}
}
QtObject {id:farm;property bool ram_only_mode:false;property bool card_access:false;signal resetGlobalImageSequenceCounterSucceeded(string newDir)}
property var system:System
property var camera:Camera
'''.replace('@CONFIG@',config)
NATIVE='''import QtQuick 2.0
QtObject {
 property int currentDialMode:0;property int DmFullauto:1;property int MENU:1
 property int CapabilityContinuousDrive:1;property int CapabilityGetSetAFmode:2
 property int lens_family:3;property int HCLens:1;property int HCCLens:2;property int XCLens:3;property bool has_divided_scan_range:true
 property real focus_point:0.5;property int SV_auto_max:0;property int SV_auto_min:0;property int afSselectedIndex:0
 property string versionID:"fixture";property bool demoOn:false
 property int Raw:1;property int RawJpg:2;property int CardNone:-1;property int Card0:0;property int Card1:1;property int CardRam:2
 property int card0Status:1;property int card1Status:1;property int STORAGE_ABSENT:0;property bool isFormatting:false
 function getDisplayValue(n,v){return String(v)} function getUntranslatedDisplayValue(n,v){return String(v)} function stringTranslated(n,v){return String(v)}
 function getVariableListModel(n){return ["A","B"]} function getMinValue(n){return 0} function getMaxValue(n){return 100} function getStepsForValue(n){return 1}
 function firstComponent(n){return 0.5} function secondComponent(n){return 0.5} function combine(x,y){return x+y}
}'''
class NativeMethods(QObject):
    def __init__(self):
        super().__init__();self.fixtureValues={};self.fixtureWrites=[]
    focusSizeChanged=pyqtSignal()
    expModeChanged=pyqtSignal()
    @pyqtSlot(result=bool)
    def isNewH6DisplayQml(self):return False
    @pyqtSlot(str,'QVariant',result=str)
    def getDisplayValue(self,n,v):return str(v)
    @pyqtSlot(str,'QVariant',result=str)
    def getUntranslatedDisplayValue(self,n,v):return str(v)
    @pyqtSlot(str,'QVariant',result=str)
    def stringTranslated(self,n,v):return str(v)
    @pyqtSlot(str,result='QVariantList')
    def getVariableListModel(self,n):return ['A','B']
    @pyqtSlot(str,result=int)
    def getMinValue(self,n):return 0
    @pyqtSlot(str,result=int)
    def getMaxValue(self,n):return 100
    @pyqtSlot(str,result=int)
    def getStepsForValue(self,n):return 1
    @pyqtSlot('QVariant',result=float)
    def firstComponent(self,n):return 0.5
    @pyqtSlot('QVariant',result=float)
    def secondComponent(self,n):return 0.5
    @pyqtSlot(float,float,result=float)
    def combine(self,x,y):return x+y

def native_type(source=NATIVE):
    attrs={}
    for kind,name,value in re.findall(r'property (int|real|bool|string) (\w+):\s*([^;\n]+)',source):
        value=json.loads(value);typ={'int':int,'real':float,'bool':bool,'string':str}[kind]
        signal=pyqtSignal();attrs[name+'Changed']=signal
        def setter(self,v,n=name):
            self.fixtureWrites.append(n);self.fixtureValues[n]=v
        attrs[name]=pyqtProperty(typ,lambda self,n=name,v=value:self.fixtureValues.get(n,v),setter,notify=signal)
    return type('NativeFixture',(NativeMethods,),attrs)

def harness(strategy):
    variant='a8' if strategy=='a8' else 'factory';work=OUT/'qml'/variant
    main=(work/'mainmenu/MainScreen.qml').read_text(encoding='utf-8')
    # About fixture API allowlist
    main = re.sub(r'(?m)^\s*suc\.(request\w+)\(\)\s*$', lambda m: m[0] if m[1] == 'requestLensFirmwareVersion' else '', main)
    start=main.index('    Connections {\n        target: (menu_loader.status');end=main.index('            Component.onDestruction: active = false',start)
    block=main[start:main.index('\n    }',end)+len('\n    }')]
    content='''import QtQuick 2.0
import "@ROOT@/mainmenu"
import "@ROOT@/common"
import "@ROOT@/settings/scripts/MenuItemImporter.js" as M
Item {
 id:root;width:640;height:480
 @MOCKS@
 @BLOCK@
 property var keptMenus:[];property var keptPages:[];property var keptNames:[]
 function closeMenu(){menu_loader.active=false}
 function category(i){return [M.cameraMenuItems,M.settingsMenuItems,M.videoMenuItems][i]}
 function openMenu(i){menu_loader.itemValues=category(i);menu_loader.subItem="";menu_loader.setSource("@ROOT@/mainmenu/Menu.qml",{"text":["CAMERA","GENERAL","VIDEO"][i],"anchors.fill":"parent"});menu_loader.x=0;menu_loader.active=true}
 function openPage(name){menu_loader.item.activateSubMenu(name,"@ROOT@/settings/SettingsGeneric.qml",name)}
 function closePage(){menu_loader.item.closeSubMenus()}
 function canOpen(){return menu_loader.item!==null && menu_loader.status===Loader.Ready}
 function constructAll(allRows){
  var mc=Qt.createComponent("@ROOT@/mainmenu/Menu.qml"); var pc=Qt.createComponent("@ROOT@/settings/SettingsGeneric.qml")
  if(mc.status!==Component.Ready || pc.status!==Component.Ready)throw new Error(mc.errorString()+pc.errorString())
  for(var i=0;i<3;i++){
   var menu=mc.createObject(root,{width:640,height:480,text:["CAMERA","GENERAL","VIDEO"][i]});
   if(allRows)menu.evaluationList.cacheBuffer=100000;
   menu.populateModel(category(i));keptMenus.push(menu)
   var entries=category(i)
   for(var j=0;j<entries.length;j++){
    var e=entries[j];if(e.demo || e.itemFile.indexOf("SettingsGeneric.qml")<0)continue
    var page=pc.createObject(root,{width:640,height:480,upperMenuLabel:menu.text,menuLabel:e.itemText});
    if(allRows)page.evaluationList.cacheBuffer=100000;
    page.populateModel(e.settingsList);keptPages.push(page);keptNames.push(e.settingsList)
   }
  }
 }
 function hideAll(){for(var i=0;i<keptMenus.length;i++)keptMenus[i].visible=false;for(i=0;i<keptPages.length;i++)keptPages[i].visible=false}
 function modelReport(){
  var out={menus:[],pages:[],mockReads:audit.mockReads,mockActions:audit.mockActions};
  for(var i=0;i<keptMenus.length;i++)out.menus.push({model:keptMenus[i].evaluationList.count,cacheBuffer:keptMenus[i].evaluationList.cacheBuffer})
  for(i=0;i<keptPages.length;i++)out.pages.push({name:keptNames[i],model:keptPages[i].evaluationList.count,cacheBuffer:keptPages[i].evaluationList.cacheBuffer})
  return JSON.stringify(out)
 }
}'''.replace('@ROOT@',work.as_uri()).replace('@MOCKS@',mocks(data())).replace('@BLOCK@',block)
    path=OUT/'harness'/strategy/'Harness.qml';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8');return path
def object_counts(root):
    seen={};pending=[root]
    while pending:
        item=pending.pop()
        if sip.isdeleted(item):continue
        ptr=int(sip.unwrapinstance(item))
        if ptr in seen:continue
        seen[ptr]=item;pending.extend(item.children())
        if hasattr(item,'childItems'):pending.extend(item.childItems())
    classes=collections.Counter(v.metaObject().className() for v in seen.values());names=collections.Counter(v.objectName() for v in seen.values() if v.objectName())
    page_rows=[]
    for item in seen.values():
        if item.objectName() not in ('SettingsGeneric_root','Menu_root'):continue
        visual=[];queue=list(item.childItems())
        while queue:
            v=queue.pop();visual.append(v);queue.extend(v.childItems())
        count=collections.Counter(v.objectName() for v in visual if v.objectName())
        page_rows.append({'kind':item.objectName(),'page':str(item.property('itemValues') or item.property('text') or ''),
            'visualDescendants':len(visual),'functionalDelegates':count['baseItem'],'menuDelegates':count['listDelegate'],'sectionItems':count['EvaluationSection'],
            'readyRowLoaders':sum(v.objectName()=='specialItem' and v.property('status')==1 for v in visual)})
    return {'qObjects':len(seen),'visualItems':sum(hasattr(v,'childItems') for v in seen.values()),'classes':dict(classes),'namedObjects':dict(names),'pages':page_rows}
def run():
    strategy=sys.argv[1];tag=sys.argv[2] if len(sys.argv)>2 else 'pilot'
    path=harness(strategy);app=QGuiApplication([]);view=QQuickView();warnings=[];keep=[]
    Native=native_type()
    for name in ('Settings','System','Camera','Lens','BodySync','Cambody','Config','ContentModel','GlobalStateInfo','DemoState','Upgrader'):
        v=Native();keep.append(v);view.rootContext().setContextProperty(name,v)
        if name in ('System','Camera'):view.rootContext().setContextProperty(name.lower(),v)
    config=property_block(data()['pages'],'configstore',{'focus_size':('int','39322050'),'GUI_idle_timeout':('int','30'),'SYS_standby_idle_timeout':('int','5'),'EVFPreviewTimeout':('int','2'),'CustomOption_FocusPeaking':('bool','true')})
    for name,source in [('configstore',config),('prodinfo','property string SuSerial:"fixture"')]:
        v=native_type(source)();keep.append(v);view.rootContext().setContextProperty(name,v)
    view.engine().warnings.connect(lambda es:warnings.extend(e.toString() for e in es))
    view.setSource(QUrl.fromLocalFile(str(path)))
    if view.status()!=QQuickView.Ready:raise RuntimeError('\n'.join(e.toString() for e in view.errors()))
    view.show();QTest.qWait(800);root=view.rootObject();cold=settled()
    if strategy in ('all_pages','all_rows'):
        root.constructAll(strategy=='all_rows');QTest.qWait(2200);visible=settled();root.hideAll();hidden=settled()
    else:
        # 各方案走同一普通页面序列，保留编译/图片缓存，结束均无打开菜单。
        for index,menu in enumerate(data()['menus']):
            root.openMenu(index)
            for i in range(200):
                if root.canOpen():break
                QTest.qWait(10)
            else:raise RuntimeError('menu did not become ready')
            for entry in menu:
                if entry.get('demo') or not entry['itemFile'].endswith('SettingsGeneric.qml'):continue
                root.openPage(entry['settingsList']);QTest.qWait(160);root.closePage();QTest.qWait(30)
            root.closeMenu();QTest.qWait(80)
        visible=None;hidden=settled()
    models=json.loads(root.modelReport());counts=object_counts(root)
    blocked={'CardFormat_root','GenericConfirm_root','DateTime','GreyBalanceTool','SpiritLevelView'}
    unexpected=[w for w in warnings if 'Implicitly defined onFoo properties in Connections are deprecated' not in w]
    assert not unexpected,unexpected
    assert models['mockActions']==0
    assert all(counts['namedObjects'].get(n,0)==0 for n in blocked)
    if strategy in ('all_pages','all_rows'):
        assert len(models['pages'])==23 and len(models['menus'])==3
        assert sum(p['model'] for p in models['pages'])==99
    if strategy=='all_rows':
        assert counts['namedObjects']['baseItem']==99
        assert counts['namedObjects']['EvaluationSection']==27
        assert counts['namedObjects']['listDelegate']==26
        assert sum(p['readyRowLoaders'] for p in counts['pages'])==99
    report={'strategy':strategy,'tag':tag,'hostQt':qVersion(),'pointerBits':ctypes.sizeof(ctypes.c_void_p)*8,'cold':cold,'visibleAll':visible,'steadyHidden':hidden,
        'deltaPrivateVsCold':hidden['median']['privateCommit']-cold['median']['privateCommit'],'objects':counts,'models':models,'warnings':unexpected,
        'forbiddenInstances':{n:counts['namedObjects'].get(n,0) for n in blocked},'hardwareRequests':0,'targetMeasured':False,
        'fixtureWrites':dict(collections.Counter(n for v in keep for n in v.fixtureWrites)),
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'catalogSha256':hashlib.sha256((OUT/'catalog.json').read_bytes()).hexdigest()}
    out=OUT/'results'/(strategy+'-'+tag+'.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'strategy':strategy,'privateMiB':hidden['median']['privateCommit']/1048576,'workingSetMiB':hidden['median']['workingSet']/1048576,
        'deltaPrivateMiB':report['deltaPrivateVsCold']/1048576,'qObjects':counts['qObjects'],'rows':counts['namedObjects'].get('baseItem',0),
        'menuRows':counts['namedObjects'].get('listDelegate',0),'sections':counts['namedObjects'].get('EvaluationSection',0),'warnings':len(unexpected)},ensure_ascii=False),flush=True)
    view.setSource(QUrl());QTest.qWait(30)
if __name__=='__main__':run()
