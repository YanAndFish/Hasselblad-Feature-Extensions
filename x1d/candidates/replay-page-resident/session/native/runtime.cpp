// 固定原厂 X1D 1.25.0 的独立七资源加载；不创建额外页面或照片请求。
#include <QtCore/qcryptographichash.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qsavefile.h>
#include <QtCore/qtimer.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlerror.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <unistd.h>
#include "resource_binding.h"
namespace {
bool registered=false,attempted=false,loaded=false;
bool enabled(){const char *v=std::getenv("HBL_REPLAY_PAGE_ENABLE");return v && !std::strcmp(v,"1");}
void status(const char *state){
    QSaveFile f(QStringLiteral("/tmp/hbl-replay-page/replay.status"));
    if(f.open(QIODevice::WriteOnly)){f.write(QByteArray(state)+" pid="+QByteArray::number(getpid())+"\n");f.commit();}
}
bool hash(const char *path,const char *expected){
    QFile f(QString::fromLatin1(path));return f.open(QIODevice::ReadOnly) && QCryptographicHash::hash(f.readAll(),QCryptographicHash::Sha256).toHex()==expected;
}
bool pages(QQmlApplicationEngine *engine){
    int count=0;
    for(QObject *root:engine->rootObjects())for(QObject *page:root->findChildren<QObject *>(QStringLiteral("MediaBrowseView_root"))){
        if(!page->property("residentConstructed").toBool() || page->property("residentSessionActive").toBool() ||
            page->property("residentImagesEnabled").toBool() || page->property("residentListCount").toInt()!=0 ||
            page->property("residentGridCount").toInt()!=0 || !page->property("residentZoomSource").toUrl().isEmpty() ||
            !page->property("residentZoomPreviewSource").toUrl().isEmpty())return false;
        ++count;
    }
    return count==2;
}
}
extern "C" bool replay_register(int,const unsigned char *,const unsigned char *,const unsigned char *) __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool replay_register(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data){
    using Function=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<Function>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if(!original)return false;
    if(enabled() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !attempted){
        attempted=true;
        if(hash("/proc/self/exe","d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b") &&
           hash("/tmp/hbl-replay-page/replay-page.rcc",rccSha))
            registered=QResource::registerResource(QStringLiteral("/tmp/hbl-replay-page/replay-page.rcc"));
    }
    return original(version,tree,names,data);
}
extern "C" void replay_load(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void replay_load(QQmlApplicationEngine *engine,const QUrl &url){
    using Function=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Function>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original){if(enabled())status("replay-page-load-symbol-failed");return;}
    if(!enabled() || loaded){original(engine,url);return;}
    loaded=true;
    if(!registered){status("replay-page-registration-failed");return;}
    for(const Entry &e:entries)if(!hash(e.path,e.sha)){status("replay-page-resource-hash-failed");return;}
    original(engine,url);
    if(engine->rootObjects().isEmpty()){status("replay-page-root-failed");return;}
    for(const Entry &e:entries){
        QQmlComponent c(engine,QUrl(QStringLiteral("qrc")+QString::fromLatin1(e.path)));
        if(!c.isReady() || c.isError()){
            for(const QQmlError &error:c.errors())std::fprintf(stderr,"%s\n",error.toString().toUtf8().constData());
            status("replay-page-component-failed");return;
        }
    }
    // 原 main.qml 异步创建两个窗口；只观察其原页面，不独立实例化。
    status("replay-page-awaiting-pages");
    auto timer=new QTimer(engine);timer->setInterval(250);timer->setProperty("attempts",0);
    QObject::connect(timer,&QTimer::timeout,engine,[timer,engine](){
        if(pages(engine)){status("replay-page-ready-resources7-components7-pages2");timer->stop();timer->deleteLater();return;}
        int n=timer->property("attempts").toInt()+1;timer->setProperty("attempts",n);
        if(n>=40){status("replay-page-prewarm-failed");timer->stop();timer->deleteLater();}
    });
    timer->start();
}
