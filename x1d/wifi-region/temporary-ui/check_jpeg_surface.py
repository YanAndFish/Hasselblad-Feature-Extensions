"""Synthetic offline images only; no camera photographs or device access."""
exec((__import__('pathlib').Path(__file__).parent/'check_settings_page.py').read_text().split('app=QGuiApplication')[0])
from PySide6.QtGui import QImage, QColor
app=QGuiApplication([])
out=P/'build/jpeg-surface-test';out.mkdir(exist_ok=True)
sample=QImage(32,24,QImage.Format_RGB32);sample.fill(QColor('red'))
assert sample.save(str(out/'sample.jpg'),'JPEG')
v=QQuickView();v.setSource(QUrl.fromLocalFile(str(P/'JpegPlaybackSurface.qml')))
assert v.status()==QQuickView.Ready,[e.toString() for e in v.errors()]
v.setResizeMode(QQuickView.SizeRootObjectToView);v.resize(320,240);v.show()
p=v.rootObject()
def black():
    QTest.qWait(100)
    assert v.grabWindow().pixelColor(160,120)==QColor('black'),'stale/non-black pixels'
black()
p.setProperty('jpegSource',QUrl.fromLocalFile(str(out/'sample.jpg')))
p.setProperty('loadRequested',True);black()
p.setProperty('jpegComplete',True)
for _ in range(30):
    QTest.qWait(20)
    if p.property('displayReady'):break
assert p.property('displayReady'),'valid JPEG failed'
assert v.grabWindow().pixelColor(160,120).red()>200
p.setProperty('jpegSource',QUrl.fromLocalFile(str(out/'missing.jpg')));black()
p.setProperty('jpegSource',QUrl.fromLocalFile(str(out/'sample.3fr')));black()
assert not p.property('acceptedSource') and p.property('displayedSource').isEmpty()
p.setProperty('jpegSource',QUrl('image://imagestore/Full/example.3fr'));black()
assert not p.property('acceptedSource')
p.setProperty('jpegSource',QUrl.fromLocalFile(str(out/'sample.jpg')))
QTest.qWait(100);assert p.property('displayReady')
p.setProperty('loadRequested',False);black()
assert p.property('displayedSource').isEmpty(),'release did not clear source'
print('PASS JPEG surface: complete JPEG, unfinished/missing black, RAW rejected, no stale photo, release')
