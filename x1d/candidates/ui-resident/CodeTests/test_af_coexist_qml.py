"""实际 AF/常驻资源叠加及两处 AF 导航；相机和 AF 后端均为显式替身。"""
from pathlib import Path
import hashlib,importlib.util,json,os,re,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'));sys.path.insert(0,str(HERE/'CodeTests'))
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ.update(QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML_DISABLE_DISK_CACHE='1')
spec=importlib.util.spec_from_file_location('af_ui_build_for_test',HERE/'af-session/build.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
from PySide6.QtCore import QObject,QUrl,QResource,QFile,QIODevice,Property,Signal,Qt,QPoint,qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
import test_original_pages as legacy
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    report=b.resources();files,af=b.inputs();checks=[]
    app=QGuiApplication.instance() or QGuiApplication([])
    def check(n,v):
        if not v:raise AssertionError(n)
        checks.append(n)
    directory=b.OUT/'qml-test';directory.mkdir(parents=True,exist_ok=True)
    delta=b.OUT/'resources/ui-af.rcc';af_rcc=b.OUT/'resources/af-only-ui.rcc'
    ui=b.load_module('af_ui_compose_test',HERE/'tools/build.py');factory=ui.baseline()
    base_rcc=directory/'factory.rcc';base_rcc.write_bytes(ui.rcc(factory))
    def read(path):
        f=QFile(':'+path);assert f.open(QIODevice.ReadOnly),path
        value=bytes(f.readAll());f.close();return value
    paths=(delta,af_rcc,base_rcc)
    for path in paths:check('actual Qt registers '+path.name,QResource.registerResource(str(path)))
    for key,expected in report['effectiveResources'].items():check('actual effective bytes '+key,hashlib.sha256(read(key)).hexdigest()==expected)
    check('effective AF menu entry exactly once',read('/settings/scripts/MenuItemSpecificationsWedge.js').count(b'name: "cameraSettingsAdvancedAF"')==1)
    for path in reversed(paths):check('unregister '+path.name,QResource.unregisterResource(str(path)))
    # 负例：AF 先注册会得到旧 SettingsGeneric；证明不能仅凭两个 register=true。
    QResource.registerResource(str(af_rcc));QResource.registerResource(str(delta))
    check('reversed order is detectably wrong',hashlib.sha256(read('/settings/SettingsGeneric.qml')).hexdigest()==report['afResources']['/settings/SettingsGeneric.qml'] and
        hashlib.sha256(read('/settings/SettingsGeneric.qml')).hexdigest()!=report['effectiveResources']['/settings/SettingsGeneric.qml'])
    QResource.unregisterResource(str(delta));QResource.unregisterResource(str(af_rcc))
    combined={k:(b.OUT/'resources/effective'/k.lstrip('/')).read_text(encoding='utf-8') for k in report['effectiveResources']}
    for k,v in af.items():
        if k!='/settings/SettingsGeneric.qml':check('AF resource unchanged '+k,combined[k]==v)
    full=dict(factory);full.update(combined)
    # 复用已审阅原厂页面测试夹具的适配方法；全部输出重定向到本轮目录。
    legacy.HERE=b.OUT;legacy.build=lambda:None;legacy.baseline=lambda:full;legacy.transform=lambda k,v:v
    loader_fixture=b.OUT/'qml/mainmenu/ResidentLoader.qml';loader_fixture.parent.mkdir(parents=True,exist_ok=True)
    loader_fixture.write_bytes(combined['/mainmenu/ResidentLoader.qml'].encode())
    work=legacy.prepare()
    for file in work.rglob('*.qml'):
        file.write_bytes(file.read_text(encoding='utf-8').replace('qrc:/',work.as_uri()+'/').encode())
    item_source=legacy.ITEMS.replace('if(name === "about")', 'if(name === "cameraSettingsAutofocus") return [row(SettingType.BUTTON,"cameraSettingsAdvancedAF","AF 设置",configstore)]\n    if(name === "about")')
    (work/'settings/scripts/MenuItemImporter.js').write_bytes(item_source.encode())
    camera=legacy.CameraMock();backend=QQmlPropertyMap();commands=[]
    for key,value in {'command':'','connected':True,'busy':False,'reading':True,'applying':False,'canApply':True,'probe':0,'fast':0,'fine':0,'activeProbe':0,'activeFast':0,'activeFine':0,
        'newDirection':False,'activeNewDirection':False,'fastAdvanceMs':65534,'fineAdvanceMs':65534,'fastAdvanceAvailable':False,'fineAdvanceAvailable':False,
        'fastPresets':[65535]*4,'finePresets':[65535]*5,'revision':1,'activeRevision':1,'generation':1,'statusText':'offline'}.items():backend.insert(key,value)
    backend.valueChanged.connect(lambda k,v:commands.append(json.loads(v)) if k=='command' and v else None)
    maps=[];warnings=[];view=QQuickView()
    for key,values in {'GlobalStateInfo':{'afSselectedIndex':0},'System':{'versionID':'fixture'},'DemoState':{'demoOn':False}}.items():
        m=QQmlPropertyMap();maps.append(m)
        for n,v in values.items():m.insert(n,v)
        view.rootContext().setContextProperty(key,m)
    for key,value in {'Camera':camera,'Upgrader':camera,'Settings':camera,'hblAf':backend}.items():view.rootContext().setContextProperty(key,value)
    class Lens(QObject):lens_familyChanged=Signal()
    lens=Lens();view.rootContext().setContextProperty('Lens',lens)
    view.engine().warnings.connect(lambda values:warnings.extend(e.toString() for e in values))
    view.setSource(QUrl.fromLocalFile(str(work/'Harness.qml')))
    check('actual resident MainScreen loader and pages compile',view.status()==QQuickView.Ready)
    view.show();QTest.qWait(200);root=view.rootObject()
    def visual(item,name):
        if item.objectName()==name:return item
        for child in item.childItems():
            found=visual(child,name)
            if found is not None:return found
        return None
    page=root.findChild(QObject,'SettingsGeneric_root');menu=root.findChild(QObject,'Menu_root')
    check('resident shells preexist without AF visibility command',page is not None and menu is not None and not commands)
    def last_visible(value):return commands[-1].get('op')=='visible' and commands[-1].get('value') is value
    def click_item(item):
        point=item.mapToScene(QPoint(int(item.width()/2),int(item.height()/2)))
        QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,QPoint(round(point.x()),round(point.y())));QTest.qWait(50)
    for cycle in range(3):
        root.openMenu('CAMERA');QTest.qWait(60);root.openPage('cameraSettingsAutofocus');QTest.qWait(100)
        button=visual(root,'buttonDelegate_menuButton')
        check('AF setting button present '+str(cycle),button is not None)
        button.clicked.emit();QTest.qWait(150)
        afpage=root.findChild(QObject,'AfSettingsPage')
        check('real Generic AF dispatch and host activated '+str(cycle),afpage is not None and afpage.property('pageActive') and last_visible(True))
        if cycle==0:
            QTest.qWait(400)  # 等待原厂子页横向动画停稳，再测真实指针命中。
            click_item(visual(root,'AfSpeedPlus0'))
            if not afpage.property('dirty'):
                target=visual(root,'AfSpeedPlus0');point=target.mapToScene(QPoint(20,20))
                print({'targetVisible':target.property('visible'),'targetEnabled':target.property('enabled'),'point':(point.x(),point.y()),'view':(view.width(),view.height()),'af':(afpage.property('visible'),afpage.property('width'),afpage.property('height')),'last':commands[-3:]})
                view.grabWindow().save(str(directory/'pointer-failure.png'))
            check('r4 editor remains clickable while reading inside resident Generic',afpage.property('dirty') and commands[-1]=={'op':'localEdit'} and afpage.property('reading') and not afpage.property('applying'))
            backend.insert('applying',True);QTest.qWait(20);before=len(commands)
            click_item(visual(root,'AfSpeedPlus0'))
            check('r4 applying still locks edits in resident Generic',len(commands)==before)
            backend.insert('applying',False);QTest.qWait(20)
        if cycle==1:root.closePage()
        else:afpage.backRequested.emit()
        QTest.qWait(150)
        check('close destroys AF subpage and hides backend '+str(cycle),root.findChild(QObject,'AfSettingsPage') is None and last_visible(False))
        root.closeMenu();QTest.qWait(80)
    check('resident generic and menu identities preserved',root.findChild(QObject,'SettingsGeneric_root')==page and root.findChild(QObject,'Menu_root')==menu)
    view.setSource(QUrl());QTest.qWait(40)
    # ControlScreen 的真实插入块原样执行，外围只提供它需要的上下文。
    control=combined['/controlscreen/ControlScreen.qml']
    block=re.search(r'    AfQuickEntry \{.*?\n    \}',control,re.S).group(0)
    quick_source='''import QtQuick 2.5
import "@DIR@"
Item {
 id: root; width:640; height:480
 QtObject { id: scope; property bool popupOpen:false }
 QtObject { id: guiconfig; property bool isWedge:true }
 QtObject { id: Camera; property bool inSession:false; property bool exposing:false }
 QtObject { id: viewModel; property bool videoMode:false }
 function unavailable() { viewModel.videoMode=true }
 @BLOCK@
}'''.replace('@DIR@',(work/'af-settings').as_uri()).replace('@BLOCK@',block)
    # QML id 不能大写；Camera 在原厂为单例，这里仍以显式上下文对象供给。
    quick_source=quick_source.replace(' QtObject { id: Camera; property bool inSession:false; property bool exposing:false }','')
    camera_state=QQmlPropertyMap();camera_state.insert('inSession',False);camera_state.insert('exposing',False)
    quickfile=work/'QuickHarness.qml';quickfile.write_bytes(quick_source.encode())
    view.rootContext().setContextProperty('Camera',camera_state);view.setSource(QUrl.fromLocalFile(str(quickfile)))
    QTest.qWait(100)
    if view.status()!=QQuickView.Ready:print([e.toString() for e in view.errors()])
    check('actual ControlScreen AF block compiles',view.status()==QQuickView.Ready)
    QTest.qWait(120);quickroot=view.rootObject();quick=quickroot.findChild(QObject,'AfQuickEntry')
    check('center entry closed initially',quick is not None and not quick.property('pageOpen'))
    QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,QPoint(320,240));QTest.qWait(150)
    afpage=quickroot.findChild(QObject,'AfSettingsPage')
    check('actual center button click opens AF page',quick.property('pageOpen') and afpage is not None and afpage.property('pageActive'))
    afpage.backRequested.emit();QTest.qWait(150)
    check('center page return closes and stops query',not quick.property('pageOpen') and last_visible(False))
    quick.openPage();QTest.qWait(100);quickroot.unavailable();QTest.qWait(100)
    check('ControlScreen context loss closes AF page',not quick.property('pageOpen') and quickroot.findChild(QObject,'AfSettingsPage') is None)
    check('no configuration apply or focus requests',all(v.get('op') in ('visible','localEdit') for v in commands))
    unexpected=[v for v in warnings if 'Implicitly defined onFoo properties in Connections are deprecated' not in v]
    if unexpected:print('\n'.join(unexpected))
    check('no unexpected QML errors',not unexpected)
    view.setSource(QUrl());QTest.qWait(40)
    proof={'passed':True,'checks':checks,'hostQt':qVersion(),'rccSha256':report['rccSha256'],'resources':report['effectiveResources'],
        'testSha256':sha(Path(__file__)),'resourcesManifestSha256':sha(b.OUT/'resources/manifest.json'),
        'hardwareRequests':0,'targetQt55Validated':False,'afCommands':commands,'afBusinessLogicChanged':False}
    b.save(b.OUT/'qml-validation.json',proof)
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
