"""离屏 Qt 指针点击真实页面，包含原厂父级拖动过滤和参数页入口。"""
import hashlib,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['QT_QUICK_BACKEND']='software';os.environ['QML_DISABLE_DISK_CACHE']='1'
from PySide6.QtCore import QObject,QUrl,QResource,Qt,QPoint,QPointF,qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtTest import QTest

def run():
    app=QGuiApplication.instance() or QGuiApplication([])
    out=HERE/'CodeTests/output';out.mkdir(parents=True,exist_ok=True)
    rcc=HERE/'build/resources/af-only-ui.rcc';assert QResource.registerResource(str(rcc))
    checks=[];commands=[]
    def check(label,value):assert value,label;checks.append(label)
    for quick in (False,True):
        for width,height in ((640,480),(800,480),(320,240)):
            view=QQuickView();view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
            backend=QQmlPropertyMap()
            data={'command':'','connected':False,'busy':True,'reading':True,'applying':False,'canApply':False,'probe':0,'fast':0,'fine':0,
                'newDirection':False,'fastAdvanceMs':65534,'fineAdvanceMs':65534,'activeProbe':0,'activeFast':0,'activeFine':0,
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
                point=item.mapToScene(QPointF(item.width()/2,item.height()/2))
                check('hit within screen '+name,0<=point.x()<width and 0<=point.y()<height)
                QTest.mouseClick(view,Qt.MouseButton.LeftButton,pos=QPoint(round(point.x()),round(point.y())));QTest.qWait(20)
            check('read waiting does not mark apply',not page.property('applying'))
            click('AfSpeedPlus0');check('pointer changes draft while read pending',page.property('draft').toVariant()[0]==5000)
            click('AfDirectionButton');check('pointer toggle while disconnected',page.property('direction'))
            check('local edits are diagnostic only',commands[-1]['op']=='localEdit')
            # First successful snapshot merges untouched fields without dropping offline edits.
            backend.insert('probe',7000);backend.insert('fast',15000);backend.insert('fine',6000);backend.insert('revision',7)
            backend.insert('connected',True);backend.insert('canApply',True);backend.insert('reading',False);QTest.qWait(230)
            check('initial snapshot preserves touched values',page.property('draft').toVariant()==[5000,15000,6000] and page.property('direction'))
            check('base revision adopted',page.property('loadedRevision')==7)
            backend.insert('reading',True);click('AfApplyButton')
            check('save carries draft revision during read',commands[-1].get('op')=='apply' and commands[-1]['expectedRevision']==7)
            backend.insert('applying',True);QTest.qWait(20)
            before=page.property('draft').toVariant();count=len(commands);click('AfSpeedPlus0')
            check('only apply blocks editing',page.property('draft').toVariant()==before and len(commands)==count)
            backend.insert('applying',False);backend.insert('revision',8);QTest.qWait(230)
            check('dirty draft keeps original revision',page.property('loadedRevision')==7)
            click('AfBackButton');QTest.qWait(30)
            check('back remains usable',root.findChild(QObject,'AfSettingsPage') is None or not page.property('pageActive'))
            view.close();view.deleteLater();QTest.qWait(30)
    QResource.unregisterResource(str(rcc))
    report={'passed':True,'checks':len(checks),'labels':checks,'qtVersion':qVersion(),'targetQt55Tested':False,
        'hardwareRequests':0,'realPointerClicks':True,'rccSha256':hashlib.sha256(rcc.read_bytes()).hexdigest()}
    (out/'qml.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='labels'}))
if __name__=='__main__':run()
