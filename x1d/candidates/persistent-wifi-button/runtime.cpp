// 固定 X1D 1.25.0 的单资源覆盖；加载失败时保留原厂入口。
#include <QtCore/qcryptographichash.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qsavefile.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcomponent.h>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <unistd.h>
#include "hashes.h"
namespace {
bool attempted=false, registered=false, loaded=false;
bool enabled() { const char *p=std::getenv("HBL_WIFI_PROBE"); return p && !std::strcmp(p,"1"); }
bool hash(const char *p,const char *h) {
    QFile f(QString::fromLatin1(p));
    return f.open(QIODevice::ReadOnly) && QCryptographicHash::hash(f.readAll(),QCryptographicHash::Sha256).toHex()==h;
}
void state(const char *s) {
    QSaveFile f(QStringLiteral("/run/hbl-wifi-probe/ui.status"));
    if(f.open(QIODevice::WriteOnly)) {
        f.write(QByteArray(s)+" pid="+QByteArray::number(getpid())+"\n"); f.commit();
    }
}
}
extern "C" bool reg(int,const unsigned char *,const unsigned char *,const unsigned char *) __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool reg(int v,const unsigned char *t,const unsigned char *n,const unsigned char *d) {
    using F=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<F>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if(!original) return false;
    if(enabled() && !attempted && v==1 && reinterpret_cast<quintptr>(t)==0x1ec7f0) {
        attempted=true;
        if(hash("/proc/self/exe",GUI_SHA) && hash("/run/hbl-wifi-probe/button.rcc",RCC_SHA))
            registered=QResource::registerResource(QStringLiteral("/run/hbl-wifi-probe/button.rcc"));
    }
    return original(v,t,n,d);
}
extern "C" void load(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void load(QQmlApplicationEngine *e,const QUrl &u) {
    using F=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<F>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original) return;
    if(!enabled() || loaded) { original(e,u); return; }
    loaded=true;
    if(!registered || !hash(":/settings/SettingsGeneric.qml",QML_SHA)) {
        if(registered) QResource::unregisterResource(QStringLiteral("/run/hbl-wifi-probe/button.rcc"));
        original(e,u); state("probe-resource-failed"); return;
    }
    original(e,u);
    if(e->rootObjects().isEmpty()) { state("probe-root-failed"); return; }
    QQmlComponent c(e,QUrl(QStringLiteral("qrc:/settings/SettingsGeneric.qml")));
    if(!c.isReady() || c.isError()) { state("probe-component-failed"); return; }
    state("probe-ready");
}
