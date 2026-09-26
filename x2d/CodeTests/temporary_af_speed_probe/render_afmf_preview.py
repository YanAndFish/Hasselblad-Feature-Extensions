
import sys,os,base64,hashlib,json
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path('x2d/outputs/4.2.0/temporary-wifi-button/qt-runtime').resolve()))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt,QRect,QBuffer,QIODevice
from PySide6.QtGui import QGuiApplication,QImage,QPainter,QFont,QColor,QFontDatabase
app=QGuiApplication([])
fid=QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
family=QFontDatabase.applicationFontFamilies(fid)[0]
im=QImage(640,480,QImage.Format_RGB32);im.fill(QColor('#101820'))
p=QPainter(im);p.setRenderHint(QPainter.Antialiasing);p.setPen(QColor('white'));p.setFont(QFont(family,25))
p.drawText(QRect(20,32,600,62),Qt.AlignCenter,'自建页面预览')
p.setFont(QFont(family,13));p.setPen(QColor('#b7c5d4'))
p.drawText(QRect(20,104,600,36),Qt.AlignCenter,'由我们的脚本跳转到这里')
p.setPen(Qt.NoPen);p.setBrush(QColor('#2864dc'));p.drawRoundedRect(QRect(40,183,260,126),18,18)
p.setBrush(QColor('#24845e'));p.drawRoundedRect(QRect(340,183,260,126),60,60)
p.setPen(QColor('white'));p.setFont(QFont(family,22))
p.drawText(QRect(40,183,260,126),Qt.AlignCenter,'测试 A')
p.drawText(QRect(340,183,260,126),Qt.AlignCenter,'测试 B')
p.setPen(QColor('#c8d2df'));p.setFont(QFont(family,14))
p.drawText(QRect(20,352,600,40),Qt.AlignCenter,'图片预览 · 两个按钮暂不可点击')
p.drawText(QRect(20,404,600,40),Qt.AlignCenter,'再次按下前键返回相机 · 不自动退出')
p.end()
buf=QBuffer();buf.open(QIODevice.WriteOnly);assert im.save(buf,'PNG')
data=bytes(buf.data());print(json.dumps({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'width':640,'height':480}))

Path('x2d/CodeTests/temporary_af_speed_probe/afmf-custom-page.png').write_bytes(data)
