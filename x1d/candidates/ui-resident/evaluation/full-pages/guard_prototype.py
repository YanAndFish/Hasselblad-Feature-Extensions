"""仅在评估副本验证用户输入信号，保留原内存测量输入不变。"""
from pathlib import Path
import difflib,hashlib,json,re,shutil,sys
sys.dont_write_bytecode=True
import measure as m
from PyQt5.QtCore import Qt,QObject,QUrl,QPointF,pyqtProperty,pyqtSignal
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest
HERE=Path(__file__).resolve().parent;OUT=HERE/'build/guard-prototype'
SOURCE=HERE/'build/qml/factory';WORK=OUT/'qml'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
    edits={};shutil.copytree(SOURCE,WORK,dirs_exist_ok=True)
    for p in WORK.rglob('*'):
        if p.suffix in ('.qml','.js'):
            p.write_text(p.read_text(encoding='utf-8').replace(SOURCE.as_uri(),WORK.as_uri()),encoding='utf-8')
    path=WORK/'settings/components/SettingSlider.qml';before=path.read_text(encoding='utf-8')
    after=before.replace('    property real value: 1','''    property real value: 1
    signal userEdited(real editedValue)
    function commitUserValue(editedValue) {
        if (!visible || !enabled || editedValue === value) return
        userEdited(editedValue)
    }''')
    assert before.count('value = newValue')==2 and before.count('value = realValue')==1
    after=after.replace('value = newValue','commitUserValue(newValue)').replace('value = realValue','commitUserValue(realValue)')
    edits[path.relative_to(WORK).as_posix()]=(before,after);path.write_text(after,encoding='utf-8')
    path=WORK/'settings/SettingsGeneric.qml';before=path.read_text(encoding='utf-8')
    assert before.count('onValueChanged: proxy[name] = value')==1
    after=before.replace('onValueChanged: proxy[name] = value','onUserEdited: proxy[name] = editedValue')
    edits[path.relative_to(WORK).as_posix()]=(before,after);path.write_text(after,encoding='utf-8')
    (OUT/'changes.patch').write_text(''.join(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=n,tofile=n)) for n,(a,b) in edits.items()),encoding='utf-8')
    path=OUT/'Harness.qml'
    text=(HERE/'build/harness/all_rows/Harness.qml').read_text(encoding='utf-8').replace(SOURCE.as_uri(),WORK.as_uri())
    path.write_text(text,encoding='utf-8');return path
def config_type(source):
    attrs={}
    for kind,name,value in re.findall(r'property (int|real|bool|string) (\w+):\s*([^;\n]+)',source):
        value=json.loads(value);typ={'int':int,'real':float,'bool':bool,'string':str}[kind]
        sig=pyqtSignal();attrs[name+'Changed']=sig
        def setter(self,v,n=name,default=value):
            self.fixtureWrites.append(n);old=self.fixtureValues.get(n,default);self.fixtureValues[n]=v
            if old!=v:getattr(self,n+'Changed').emit()
        attrs[name]=pyqtProperty(typ,lambda self,n=name,v=value:self.fixtureValues.get(n,v),setter,notify=sig)
    return type('NotifyConfigFixture',(m.NativeMethods,),attrs)
def run():
    original={p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    path=prepare();app=QGuiApplication([]);view=QQuickView();keep=[];warnings=[]
    for name in ('Settings','System','Camera','Lens','BodySync','Cambody','Config','ContentModel','GlobalStateInfo','DemoState','Upgrader'):
        v=m.native_type()();keep.append(v);view.rootContext().setContextProperty(name,v)
        if name in ('System','Camera'):view.rootContext().setContextProperty(name.lower(),v)
    source=m.property_block(m.data()['pages'],'configstore',{'focus_size':('int','39322050'),'GUI_idle_timeout':('int','30'),'SYS_standby_idle_timeout':('int','5'),'EVFPreviewTimeout':('int','2'),'CustomOption_FocusPeaking':('bool','true')})
    config=config_type(source)();keep.append(config);view.rootContext().setContextProperty('configstore',config)
    prod=m.native_type('property string SuSerial:"fixture"')();keep.append(prod);view.rootContext().setContextProperty('prodinfo',prod)
    view.engine().warnings.connect(lambda es:warnings.extend(e.toString() for e in es))
    view.setSource(QUrl.fromLocalFile(str(path)));assert view.status()==QQuickView.Ready,view.errors()
    view.show();QTest.qWait(600);root=view.rootObject();root.constructAll(True);QTest.qWait(2400)
    assert not config.fixtureWrites,config.fixtureWrites
    counts=m.object_counts(root);assert counts['namedObjects']['baseItem']==99
    root.hideAll();QTest.qWait(150)
    seen={};pending=[root]
    while pending:
        item=pending.pop();ptr=int(m.sip.unwrapinstance(item))
        if ptr in seen:continue
        seen[ptr]=item;pending.extend(item.children())
        if hasattr(item,'childItems'):pending.extend(item.childItems())
    sliders=[v for v in seen.values() if v.objectName()=='settingsSlider'];assert len(sliders)==2,len(sliders)
    checks=[]
    for slider in sliders:
        page=slider.parentItem()
        while page.objectName()!='SettingsGeneric_root':page=page.parentItem()
        pname=page.property('itemValues');name={'cameraSettingsImage':'crop_mode_opacity','generalSettingsDisplay':'BACKLIGHT_brightness'}[pname]
        config.fixtureValues[name]=40;getattr(config,name+'Changed').emit();QTest.qWait(50)
        assert slider.property('value')==40 and not config.fixtureWrites
        slider.commitUserValue(41);assert not config.fixtureWrites
        page.setVisible(True);slider.forceActiveFocus();QTest.qWait(50)
        QTest.keyClick(view,Qt.Key_Right);QTest.qWait(50)
        assert config.fixtureWrites==[name] and config.fixtureValues[name]==40, (name,config.fixtureWrites,config.fixtureValues[name])
        # int 后端按原声明转换 40.5 为 40；第二次测试用左键产生可表示变化。
        config.fixtureWrites.clear();QTest.keyClick(view,Qt.Key_Left);QTest.qWait(50)
        assert config.fixtureWrites==[name] and config.fixtureValues[name]==39
        assert slider.property('value')==39
        config.fixtureWrites.clear();config.fixtureValues[name]=70;getattr(config,name+'Changed').emit();QTest.qWait(50)
        assert slider.property('value')==70 and not config.fixtureWrites
        slider.setEnabled(False);slider.commitUserValue(71);assert not config.fixtureWrites
        slider.setEnabled(True);slider.commitUserValue(70);assert not config.fixtureWrites
        # 与拖动结束共用的提交函数，验证一次提交及外部回读；鼠标路径另行实测。
        slider.commitUserValue(71);assert config.fixtureWrites==[name] and slider.property('value')==71
        config.fixtureWrites.clear()
        descendants=[];queue=list(slider.childItems())
        while queue:
            v=queue.pop();descendants.append(v);queue.extend(v.childItems())
        marker=next(v for v in descendants if v.width()==36 and v.height()==36)
        start=marker.mapToScene(QPointF(18,18)).toPoint();end=start+QPointF(-45,0).toPoint()
        QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(view,start+QPointF(-20,0).toPoint(),60)
        QTest.mouseMove(view,end,60);QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,end);QTest.qWait(100)
        assert config.fixtureWrites==[name] and config.fixtureValues[name]<71,(name,start,end,config.fixtureWrites,config.fixtureValues[name])
        config.fixtureWrites.clear();config.fixtureValues[name]=50;getattr(config,name+'Changed').emit();QTest.qWait(50)
        assert slider.property('value')==50 and not config.fixtureWrites
        config.fixtureWrites.clear();page.setVisible(False);QTest.qWait(50)
        slider.commitUserValue(72);assert not config.fixtureWrites
        checks.append({'page':pname,'property':name,'initialWrites':0,'hiddenBackendRefresh':True,'hiddenInputBlocked':True,'keyboardPath':True,'bindingPreservedAfterInput':True,'disabledInputBlocked':True,'unchangedInputBlocked':True,'dragCommitFunction':True,'mouseDragMeasured':True})
    unexpected=[s for s in warnings if 'Implicitly defined onFoo properties in Connections are deprecated' not in s]
    assert not unexpected,unexpected
    assert original=={p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    report={'checks':checks,'allFunctionalRowsReady':sum(p['readyRowLoaders'] for p in counts['pages'])==99,'preconstructionWrites':0,'warnings':unexpected,'hardwareRequests':0,'productionChanged':False,'originalMeasurementInputsUnchanged':True,'hostQt':m.qVersion(),'sourceSha256':sha(Path(__file__)),'patchSha256':sha(OUT/'changes.patch')}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));view.setSource(QUrl());QTest.qWait(50)
if __name__=='__main__':run()
