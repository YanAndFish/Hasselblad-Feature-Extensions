"""Synthetic lifecycle test: eager construction, no background activation,
same instance on repeated opening and after switching to another popover."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
folder=P/'build/parameter-residency-test';folder.mkdir(exist_ok=True)
(folder/'ResidentPopupHost.qml').write_text((P/'ResidentPopupHost.qml').read_text(),encoding='utf-8')
for name in ['First','Second']:
    (folder/(name+'.qml')).write_text('import QtQuick 2.5\nItem {property bool preloadOnly:false; property int opens:0; function present(){opens++;visible=true} function close(){visible=false} Component.onCompleted:if(!preloadOnly)present()}')
(folder/'Test.qml').write_text('''import QtQuick 2.5
ResidentPopupHost {width:640;height:480;preloadSources:[Qt.resolvedUrl("First.qml"),Qt.resolvedUrl("Second.qml")]}''')
app=QGuiApplication([]);view=QQuickView();view.setSource(QUrl.fromLocalFile(str(folder/'Test.qml')))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
root=view.rootObject();QTest.qWait(200)
assert root.property('preloadIndex')==2
first=root.acquire(QUrl.fromLocalFile(str(folder/'First.qml')))
assert first.property('opens')==0 and not first.property('visible')
root.setProperty('source',QUrl.fromLocalFile(str(folder/'First.qml')));root.setProperty('active',True);QTest.qWait(50)
assert root.property('item')==first and first.property('opens')==1
root.setProperty('active',False);QTest.qWait(50);assert not first.property('visible')
root.setProperty('active',True);QTest.qWait(50);assert root.property('item')==first and first.property('opens')==2
root.setProperty('source',QUrl.fromLocalFile(str(folder/'Second.qml')));QTest.qWait(50)
assert not first.property('visible') and root.property('item')!=first
root.setProperty('source',QUrl.fromLocalFile(str(folder/'First.qml')));QTest.qWait(50)
assert root.property('item')==first and first.property('opens')==3
print('PASS resident popovers: passive preload, reuse, hide and switch; synthetic only')
