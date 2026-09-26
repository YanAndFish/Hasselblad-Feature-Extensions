// X1D 1.25.0 原厂 GUI 专用。只注册固定六资源，不实例化额外业务页面。
#include <QtCore/qcryptographichash.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qsavefile.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlerror.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <unistd.h>

namespace {
const char *root="/tmp/hbl-ui-full-r1";
bool registered=false, attempted=false, loaded=false;
bool enabled() { const char *v=std::getenv("HBL_UI_RESIDENT_ENABLE");return v && !std::strcmp(v,"1"); }
void status(const char *state) {
    QSaveFile f(QString::fromLatin1(root)+QStringLiteral("/ui.status"));
    if(f.open(QIODevice::WriteOnly)) {
        const QByteArray text=QByteArray(state)+" pid="+QByteArray::number(getpid())+"\n";
        f.write(text); f.commit();
    }
}
bool hash(const char *path,const char *expected) {
    QFile f(QString::fromLatin1(path));
    return f.open(QIODevice::ReadOnly) && QCryptographicHash::hash(f.readAll(),QCryptographicHash::Sha256).toHex()==expected;
}
struct Entry { const char *path; const char *sha; };
const Entry entries[]={
    {":/mainmenu/MainScreen.qml","3f88336ef0d1fe0d17f7070fe3190f013a67e866cbb91a6986e220b2082ebda2"},
    {":/mainmenu/Menu.qml","5914c0c05674f5c3be3d2e4316ba6c872037ea0365dfa7bc374631b8bce811b3"},
    {":/settings/SettingsGeneric.qml","2bb82bfc349005fb58dabd8180a68e3f36bca28f0cd1926898f3cc57616cad3b"},
    {":/mainmenu/ResidentLoader.qml","b6de4ff99ba49fc1468d7f8c44c75f71d1a6bacfd8171727a5f2b3b01d0b478d"},
    {":/settings/components/SettingSlider.qml","2c57dd18ae5a681ff009c4ca2ed6a0bea132c21be6cdbb24c9cdf6604f5a527d"},
    {":/settings/scripts/MenuItemImporter.js","e1b689d9f8861957a7ab8c1ee0ddebb58233f32d7c8e92d2867421080df01d3b"}
};
}
#include "readiness.h"
extern "C" bool ui_register(int,const unsigned char *,const unsigned char *,const unsigned char *)
    __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool ui_register(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data) {
    using Function=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<Function>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if(!original) return false;
    // 此地址只对摘要固定的非 PIE victory-gui 成立；装载器前置核验同一二进制。
    if(enabled() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !attempted) {
        attempted=true;
        if(hash("/proc/self/exe","d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b") &&
           hash("/tmp/hbl-ui-full-r1/ui-resident.rcc","1c794a21fe7f61a4bdab50f40b5eb02bc428fcd584e9ed2d9d8119c97223b551"))
            registered=QResource::registerResource(QStringLiteral("/tmp/hbl-ui-full-r1/ui-resident.rcc"));
    }
    return original(version,tree,names,data);
}
extern "C" void ui_load(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void ui_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Function=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Function>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original) { if(enabled()) status("ui-resident-load-symbol-failed");return; }
    if(!enabled()) { original(engine,url);return; }
    if(loaded) { original(engine,url);return; }
    loaded=true;
    if(!registered) { status("ui-resident-registration-failed");return; }
    for(const Entry &e:entries) if(!hash(e.path,e.sha)) { status("ui-resident-resource-hash-failed");return; }
    // 正常 main.qml 提供 constants/configstore 等原厂上下文；不独立 create 页面。
    BootGate *gate = new BootGate(engine);
    original(engine,url);
    if(engine->rootObjects().isEmpty()) { status("ui-resident-root-failed");return; }
    for(const Entry &e:entries) {
        if(!QString::fromLatin1(e.path).endsWith(QStringLiteral(".qml"))) continue;
        QQmlComponent c(engine,QUrl(QStringLiteral("qrc")+QString::fromLatin1(e.path)));
        if(!c.isReady() || c.isError()) {
            std::fprintf(stderr,"UI resident component failed: %s\n",e.path);
            for(const QQmlError &error:c.errors()) std::fprintf(stderr,"%s\n",error.toString().toUtf8().constData());
            status("ui-resident-component-failed");return;
        }
    }
    gate->start();
}
