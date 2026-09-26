"""离屏 Qt 指针点击真实页面，包含原厂父级拖动过滤和参数页入口。"""
import hashlib,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_QUICK_BACKEND']='software';os.environ['QML_DISABLE_DISK_CACHE']='1'
from PySide6.QtCore import QObject,QUrl,QResource,Qt,QPoint,QPointF,qVersion
from PySide6.QtGui import QGuiApplication,QFontDatabase,QFont
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtTest import QTest

def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc');assert font>=0
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0]))
    out=HERE/'CodeTests/output';out.mkdir(parents=True,exist_ok=True)
    rcc=HERE/'ui/build/resources/af-only-ui.rcc';assert QResource.registerResource(str(rcc))
    checks=[];commands=[]
    def check(label,value):assert value,label;checks.append(label)
    for quick in (False,True):
        for width,height in ((640,480),(800,480),(320,240)):
            view=QQuickView();view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
            backend=QQmlPropertyMap()
            data={'command':'','connected':False,'busy':True,'reading':True,'applying':False,'canApply':False,'probe':0,'fast':0,'fine':0,
                'startSpeed':0,'startSamples':3,'activeStartSpeed':0,'activeStartSamples':3,'newDirection':False,'fastAdvanceMs':65534,'fineAdvanceMs':65534,'activeProbe':0,'activeFast':0,'activeFine':0,
                'fastPresets':[65535]*4,'finePresets':[65535]*5,'revision':1,'statusText':'读取等待'}
            for key,value in data.items():backend.insert(key,value)
            backend.valueChanged.connect(lambda key,value:commands.append(json.loads(value)) if key=='command' and value else None)
            view.rootContext().setContextProperty('hblAf',backend)
            component=('AfQuickEntry { id: entry; anchors.fill: parent }' if quick else '''MouseArea {
                anchors.fill: parent
                drag.target: loader;drag.axis: Drag.XAxis;drag.minimumX: 0;drag.maximumX: parent.width;drag.filterChildren: true
                Loader { id: loader;anchors.fill: parent;source: "qrc:/af-settings/AfSettingsHost.qml"
                    onLoaded: { item.populateModel("cameraSettingsAdvancedAF");item.afCloseRequested.connect(function(){loader.active=false}) }
                }
            }''')
            harness=out/'pointer.qml';harness.write_text('import QtQuick 2.5\nimport "qrc:/af-settings"\nRectangle { width:640;height:480; color:"black"\n'+component+'\n}',encoding='utf-8')
            view.setSource(QUrl.fromLocalFile(str(harness)));view.resize(width,height);view.show();QTest.qWait(80)
            check('harness loaded',not view.errors())
            if quick:QTest.mouseClick(view,Qt.MouseButton.LeftButton,pos=QPoint(width//2,height//2));QTest.qWait(80)
            root=view.rootObject();page=root.findChild(QObject,'AfSettingsPage')
            check('page active '+str((quick,width,height)),page is not None and page.property('pageActive'))
            def find(item,name):
                if item.objectName()==name:return item
                for child in item.childItems():
                    value=find(child,name)
                    if value is not None:return value
            def click(name):
                item=find(root,name);check('hit area '+name,item is not None)
                scroll=find(root,'AfSettingsScroll')
                if name not in ('AfApplyButton','AfReadButton','AfBackButton'):
                    local=item.mapToItem(scroll,QPointF(item.width()/2,item.height()/2))
                    target=scroll.property('contentY')+local.y()-scroll.height()/2
                    scroll.setProperty('contentY',max(0,min(scroll.property('contentHeight')-scroll.height(),target)));QTest.qWait(20)
                point=item.mapToScene(QPointF(item.width()/2,item.height()/2))
                check('hit within screen '+name,0<=point.x()<width and 0<=point.y()<height)
                QTest.mouseClick(view,Qt.MouseButton.LeftButton,pos=QPoint(round(point.x()),round(point.y())));QTest.qWait(20)
            scroll=find(root,'AfSettingsScroll');scale=min(width/640,height/480);origin=(width-640*scale)/2
            point=lambda x,y:QPoint(round(origin+x*scale),round(y*scale))
            QTest.mousePress(view,Qt.MouseButton.LeftButton,pos=point(120,350))
            for y in (330,300,270,240,210):QTest.mouseMove(view,point(120,y),30)
            QTest.mouseRelease(view,Qt.MouseButton.LeftButton,pos=point(120,210));QTest.qWait(250)
            check('vertical drag scrolls within factory parent',scroll.property('contentY')>30)
            scroll.setProperty('contentY',0);QTest.qWait(30)
            if width==640 and not quick:view.grabWindow().save(str(out/'ui-top.png'))
            check('read waiting does not mark apply',not page.property('applying'))
            click('AfStartSpeedPlus');check('low speed independent',page.property('startSpeed')==1000)
            click('AfStartSamplesPlus');check('effective sample adjustment',page.property('startSamples')==4)
            click('AfSpeedPlus0');check('pointer changes draft while read pending',page.property('draft').toVariant()[0]==5000)
            check('retired direction control absent',find(root,'AfDirectionButton') is None)
            if width==640 and not quick:view.grabWindow().save(str(out/'ui-bottom.png'))
            check('retired direction state absent',page.property('direction') is None)
            check('local edits are diagnostic only',commands[-1]['op']=='localEdit')
            # First successful snapshot merges untouched fields without dropping offline edits.
            backend.insert('newDirection',True);backend.insert('probe',7000);backend.insert('fast',15000);backend.insert('fine',6000);backend.insert('revision',7)
            backend.insert('connected',True);backend.insert('canApply',True);backend.insert('reading',False);QTest.qWait(230)
            check('initial snapshot preserves touched values',page.property('draft').toVariant()==[5000,15000,6000])
            check('base revision adopted',page.property('loadedRevision')==7)
            for target in (7000,9000,11000,13000,15000,17000,20000):
                click('AfSpeedPlus0');check('probe option '+str(target),page.property('draft').toVariant()[0]==target)
            click('AfSpeedPlus0');check('probe bounded at 20000',page.property('draft').toVariant()[0]==20000)
            for target in (17000,15000,13000):
                click('AfSpeedMinus0');check('probe reverse option '+str(target),page.property('draft').toVariant()[0]==target)
            backend.insert('reading',True);click('AfApplyButton')
            check('save carries draft revision during read',commands[-1].get('op')=='apply' and commands[-1]['expectedRevision']==7 and commands[-1]['startSpeed']==1000 and commands[-1]['startSamples']==4 and commands[-1]['newDirection'] is False)
            backend.insert('applying',True);QTest.qWait(20)
            before=page.property('draft').toVariant();count=len(commands);click('AfSpeedPlus0')
            check('only apply blocks editing',page.property('draft').toVariant()==before and len(commands)==count)
            backend.insert('applying',False);backend.insert('revision',8);QTest.qWait(230)
            check('dirty draft keeps original revision',page.property('loadedRevision')==7)
            count=len([x for x in commands if x['op']=='apply'])
            click('AfStartAuto');check('automatic low selects report scale and ten samples',page.property('startSpeed')==65533 and page.property('startSamples')==10)
            check('automatic choice does not apply',len([x for x in commands if x['op']=='apply'])==count)
            click('AfApplyButton');check('automatic values submitted explicitly',commands[-1]['startSpeed']==65533 and commands[-1]['startSamples']==10)
            if width==640 and not quick:
                scroll.setProperty('contentY',0);QTest.qWait(30);view.grabWindow().save(str(out/'ui-auto.png'))
            click('AfStartSpeedMinus');check('manual speed remains selectable',page.property('startSpeed')==1000)
            click('AfBackButton');QTest.qWait(30)
            check('back remains usable',root.findChild(QObject,'AfSettingsPage') is None or not page.property('pageActive'))
            view.close();view.deleteLater();QTest.qWait(30)
    QResource.unregisterResource(str(rcc))
    report={'passed':True,'checks':len(checks),'labels':checks,'qtVersion':qVersion(),'targetQt55Tested':False,
        'hardwareRequests':0,'realPointerClicks':True,'rccSha256':hashlib.sha256(rcc.read_bytes()).hexdigest()}
    (out/'qml.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='labels'}))
if __name__=='__main__':run()
