"""Offline proxy test. Does not change any camera setting."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtQml import QQmlPropertyMap
app=QGuiApplication([])
out=P/'build/format-test';out.mkdir(exist_ok=True)
source=(P/'CaptureFormatPolicy.qml').read_text()
(out/'CaptureFormatPolicy.qml').write_text('\n'.join(l for l in source.splitlines() if not l.startswith('import com.')))
store=QQmlPropertyMap();store.insert('image_format',0)
system=QQmlPropertyMap();system.insert('system_state',0);system.insert('StateUp',2)
camera=QQmlPropertyMap();camera.insert('inSession',False);camera.insert('exposing',False)
config=QQmlPropertyMap();config.insert('RawJpg',2)
v=QQuickView()
for name,obj in [('configstore',store),('System',system),('Camera',camera),('Config',config)]:v.rootContext().setContextProperty(name,obj)
v.setSource(QUrl.fromLocalFile(str(out/'CaptureFormatPolicy.qml')))
assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
QTest.qWait(30);assert store.value('image_format')==0,'must wait for startup'
camera.insert('inSession',True);system.insert('system_state',2)
QTest.qWait(30);assert store.value('image_format')==0,'must not alter active capture'
camera.insert('inSession',False)
QTest.qWait(30);assert store.value('image_format')==2,'apply RAW+JPEG'
camera.insert('exposing',True);store.insert('image_format',0)
QTest.qWait(30);assert store.value('image_format')==0,'must not alter exposure'
camera.insert('exposing',False)
QTest.qWait(30);assert store.value('image_format')==2,'restore after exposure'
store.insert('image_format',0)
QTest.qWait(30);assert store.value('image_format')==2,'restore after external change'
print('PASS format policy: startup, capture/exposure guard, actual write and reset correction')
