// X1D 1.25.0: dedicated JPEG-only provider; never calls the RAW image API.
#include "jpeg_provider.h"
#include "../../candidates/replay-reader/native/jpeg_container.h"
#include <QtQuick/QQuickImageProvider>
#include <QtQml/QQmlEngine>
#include <QtCore/QBuffer>
#include <QtCore/QElapsedTimer>
#include <QtCore/QUrl>
#include <QtCore/QDebug>
#include <QtCore/QMutex>
#include <QtCore/QMutexLocker>
#include <QtGui/QImageReader>
#include <QtDBus/QDBusConnection>
#include <QtDBus/QDBusMessage>
#ifdef HBL_JPEG_PROBE
#include <QtCore/QFile>
static QString probeFile;
static int probeReads=0;
#endif

// Public exported methods, verified against the firmware 1.25.0 libraries.
class Bus {
public:
    static QDBusConnection bus();
    static const QString &storageService();
    static const QString &storagePath();
    static const QString &storageInterface();
};
namespace {
QString pairedPath(const QString &id) {
    const QString path=QUrl::fromPercentEncoding(id.toUtf8());
    if(!path.startsWith('/') || path.contains("//") || path.contains('\\') || path.contains(QChar(0)) || path.size()>1024)return QString();
    for(const QString &part:path.split('/'))if(part==".." || part==".")return QString();
    if(path.endsWith(".jpg",Qt::CaseInsensitive))return path;
    // Match the earlier candidate reader's storage-name convention. A GUI/display
    // suffix is not evidence of the storage service's actual file spelling.
    if(path.endsWith(".3fr",Qt::CaseInsensitive))return path.left(path.size()-4)+".jpg";
    return QString();
}
QByteArray readJpeg(const QString &path, int fileBytes) {
    QByteArray result;
    QElapsedTimer time;time.start();
    const int chunk=1024*1024, limit=128*1024*1024;
    while(result.size()<limit && time.elapsed()<8000) {
        // Firmware File rejects a request extending past EOF instead of
        // returning a short read. Use the paired JPEG's cached SizeRole.
        const int count=fileBytes>0?qMin(chunk,fileBytes-result.size()):chunk;
        if(count<=0)return QByteArray();
#ifdef HBL_JPEG_PROBE
        // Isolated probe build reads only its generated fixture in RAM.
        if(path!=QStringLiteral("/fixture/test.jpg"))return QByteArray();
        QFile fixture(probeFile);
        if(!fixture.open(QIODevice::ReadOnly) || !fixture.seek(result.size()))return QByteArray();
        ++probeReads;
        const QByteArray bytes=fixture.read(count);
#else
        QDBusMessage call=QDBusMessage::createMethodCall(Bus::storageService(),Bus::storagePath(),Bus::storageInterface(),QStringLiteral("File"));
        call << path << QVariant::fromValue<qulonglong>(result.size()) << count;
        const QDBusMessage reply=Bus::bus().call(call,QDBus::Block,1500);
        const QList<QVariant> args=reply.arguments();
        if(reply.type()!=QDBusMessage::ReplyMessage || args.size()!=1 || args[0].type()!=QVariant::ByteArray){
            // Error class and type only: never emit paths, messages or pixels.
            qWarning("JpegRead reply=%d argc=%d type=%d error=%s",int(reply.type()),args.size(),args.isEmpty()?-1:int(args[0].type()),qPrintable(reply.errorName()));
            const QString message=reply.errorMessage().toLower();
            qWarning("JpegRead category missing=%d timeout=%d busy=%d denied=%d invalid=%d",message.contains("not found")||message.contains("no such")||message.contains("exist"),message.contains("timeout")||message.contains("timed out"),message.contains("busy"),message.contains("denied")||message.contains("permission"),message.contains("invalid"));
            qWarning("JpegRead detail large=%d transfer=%d connect=%d unsupported=%d bus=%d",message.contains("large")||message.contains("big"),message.contains("transfer"),message.contains("connect")||message.contains("socket")||message.contains("server"),message.contains("supported"),Bus::bus().isConnected());
            return QByteArray();
        }
        const QByteArray bytes=args[0].toByteArray();
#endif
        if(bytes.size()>count || bytes.isEmpty()){qWarning("JpegRead empty or oversized reply");return QByteArray();}
        result+=bytes;
        XjInfo info;
        if(xj_inspect(reinterpret_cast<const uint8_t*>(result.constData()),result.size(),&info)==0)return result;
        if(bytes.size()<count){qWarning("JpegRead incomplete container");return QByteArray();}
    }
    return QByteArray();
}
class JpegProvider final:public QQuickImageProvider {
    QMutex regionMutex;
    QString regionIdentity;
    QByteArray regionData;
public:
    JpegProvider():QQuickImageProvider(Image,ForceAsynchronousImageLoading){}
    QImage requestImage(const QString &id,QSize *size,const QSize &requested) override {
        QElapsedTimer timing;timing.start();
        if(size)*size=QSize();
        if(id.startsWith("release/")){
            QMutexLocker lock(&regionMutex);regionIdentity.clear();regionData.clear();
            QImage empty(1,1,QImage::Format_RGB32);empty.fill(Qt::black);if(size)*size=empty.size();return empty;
        }
        QString identity=id;int fileBytes=0;
        QRectF region;
        if(identity.startsWith("region/")){
            QStringList fields=identity.split('/');
            if(fields.size()<6)return QImage();
            double values[4];
            for(int i=0;i<4;++i){bool ok=false;int value=fields[i+1].toInt(&ok);if(!ok || value<0 || value>1000000)return QImage();values[i]=value/1000000.0;}
            region=QRectF(values[0],values[1],values[2],values[3]);
            if(region.isEmpty() || region.right()>1.000001 || region.bottom()>1.000001)return QImage();
            identity=fields.mid(5).join('/');
        }
        const QString cacheIdentity=identity;
        if(identity.startsWith("bytes/")){
            const int separator=identity.indexOf('/',6);bool ok=false;
            fileBytes=identity.mid(6,separator-6).toInt(&ok);
            if(separator<7 || !ok || fileBytes<=0 || fileBytes>128*1024*1024)return QImage();
            identity=identity.mid(separator+1);
        }
        const QString path=pairedPath(identity);
        if(path.isEmpty()){qWarning("JpegRead invalid identity");return QImage();}
        QByteArray data;
        if(!region.isEmpty()){
            QMutexLocker lock(&regionMutex);
            if(regionIdentity==cacheIdentity)data=regionData;
            else {regionIdentity.clear();regionData.clear();data=readJpeg(path,fileBytes);if(!data.isEmpty()){regionIdentity=cacheIdentity;regionData=data;}}
        }else data=readJpeg(path,fileBytes);
        if(data.isEmpty())return QImage();
        const qint64 readTime=timing.elapsed();
        QBuffer buffer(&data);buffer.open(QIODevice::ReadOnly);
        QImageReader reader(&buffer,"JPEG");reader.setAutoTransform(true);
        const QSize original=reader.size();
        if(!original.isValid() || qint64(original.width())*original.height()>60000000)return QImage();
        QSize target=requested.isValid()?requested:QSize(1280,960);
        if(!region.isEmpty()){
            XjInfo info;
            if(xj_inspect(reinterpret_cast<const uint8_t*>(data.constData()),data.size(),&info)!=0 || !reader.supportsOption(QImageIOHandler::ClipRect))return QImage();
            double x=region.x(),y=region.y(),w=region.width(),h=region.height();
            switch(info.orientation){
                case 2:region=QRectF(1-x-w,y,w,h);break;
                case 3:region=QRectF(1-x-w,1-y-h,w,h);break;
                case 4:region=QRectF(x,1-y-h,w,h);break;
                case 5:region=QRectF(y,x,h,w);break;
                case 6:region=QRectF(y,1-x-w,h,w);break;
                case 7:region=QRectF(1-y-h,1-x-w,h,w);break;
                case 8:region=QRectF(1-y-h,x,h,w);break;
            }
            QRect clip=QRectF(region.x()*original.width(),region.y()*original.height(),region.width()*original.width(),region.height()*original.height()).toAlignedRect().intersected(QRect(QPoint(),original));
            if(clip.isEmpty() || qint64(clip.width())*clip.height()>8000000)return QImage();
            reader.setClipRect(clip);
        }else{
            target=target.boundedTo(original);
            reader.setScaledSize(original.scaled(target,Qt::KeepAspectRatio));
        }
        QImage image=reader.read();
        if(image.isNull())qWarning("JpegRead decode failed");
        else {qWarning("JpegRead decoded successfully");qWarning("JpegTiming read_ms=%lld decode_ms=%lld region=%d",static_cast<long long>(readTime),static_cast<long long>(timing.elapsed()-readTime),!region.isEmpty());}
        if(size)*size=image.size();
        return image;
    }
};
}
void installJpegPlaybackProvider(QQmlEngine *engine) {
    if(!engine->imageProvider(QStringLiteral("hbljpeg")))
        engine->addImageProvider(QStringLiteral("hbljpeg"),new JpegProvider);
}
#ifdef HBL_JPEG_PROBE
#include <QtGui/QGuiApplication>
#include <cstdio>
int main(int argc,char **argv) {
    QGuiApplication app(argc,argv);
    if(argc!=2)return 2;
    probeFile=QString::fromLocal8Bit(argv[1]);
    QImage fixture(160,120,QImage::Format_RGB32);fixture.fill(Qt::red);
    for(int y=0;y<120;++y)for(int x=80;x<160;++x)fixture.setPixel(x,y,qRgb(0,0,255));
    if(!fixture.save(probeFile,"JPEG"))return 3;
    JpegProvider provider;QSize size;
    QImage image=provider.requestImage("/fixture/test.3fr",&size,QSize(80,60));
    if(image.isNull() || size!=QSize(80,60) || qRed(image.pixel(20,20))<220)return 4;
    const int fileBytes=QFile(probeFile).size();
    if(provider.requestImage("bytes/"+QString::number(fileBytes)+"/%2Ffixture%2Ftest.jpg",&size,QSize(80,60)).isNull())return 8;
    QString sized="bytes/"+QString::number(fileBytes)+"/%2Ffixture%2Ftest.jpg";
    QImage right=provider.requestImage("region/500000/0/500000/1000000/"+sized,&size,QSize());
    if(right.size()!=QSize(80,120) || qBlue(right.pixel(40,60))<220)return 9;
    int cachedReads=probeReads;
    QImage left=provider.requestImage("region/0/0/500000/1000000/"+sized,&size,QSize());
    if(left.size()!=QSize(80,120) || qRed(left.pixel(30,60))<220 || probeReads!=cachedReads)return 10;
    provider.requestImage("release/1",&size,QSize());
    provider.requestImage("region/0/0/500000/1000000/"+sized,&size,QSize());
    if(probeReads<=cachedReads)return 11;
    int reads=probeReads;
    if(!provider.requestImage("/fixture/../test.3fr",&size,QSize()).isNull() || reads!=probeReads)return 5;
    if(!provider.requestImage("/fixture/missing.3fr",&size,QSize()).isNull())return 6;
    QFile input(probeFile);input.open(QIODevice::ReadOnly);QByteArray data=input.readAll();input.close();
    data.chop(2);QFile output(probeFile);output.open(QIODevice::WriteOnly);output.write(data);output.close();
    if(!provider.requestImage("/fixture/test.3fr",&size,QSize()).isNull())return 7;
    std::puts("PASS Qt5 JPEG: screen decode, 1:1 region pixels, compressed reuse/release, missing/incomplete black; synthetic only");
    return 0;
}
#endif
