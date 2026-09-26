"""Synthetic exposure deviation; no camera settings or images."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
app=QGuiApplication([]);view=QQuickView()
view.setSource(QUrl.fromLocalFile(str(P/'ExposureRuler.qml')))
assert view.status()==QQuickView.Ready,[e.toString() for e in view.errors()]
root=view.rootObject();text=root.findChild(QObject,'ExposureRulerValue')
assert text.property('text')=='—'
root.setProperty('valid',True)
for number,position in [(-2,10),(0,100),(2,190),(4,190)]:
    root.setProperty('value',number)
    assert abs(root.property('indicatorX')-position)<.01
assert text.property('text')=='▶ +4.0'
root.setProperty('valid',False);assert text.property('text')=='—'
print('PASS ruler: invalid, zero, signed deviation and overflow bound')
