// 叠加在固定 f325 AF GUI 的前方；不替代 AF 库，不创建第二份 AF 上下文。
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <QtCore/qcryptographichash.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qsavefile.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlerror.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <unistd.h>
namespace {
bool registered=false,attempted=false,loaded=false;
struct Entry { const char *path; const char *sha; };
#include "resources.h"
bool enabled() { const char *v=std::getenv("HBL_UI_AF_ENABLE");return v && !std::strcmp(v,"1"); }
bool setting(const char *name) { const char *v=std::getenv(name);return v && !std::strcmp(v,"1"); }
bool afNext(void *symbol) {
    Dl_info info={};return symbol && dladdr(symbol,&info) && info.dli_fname &&
        !std::strcmp(info.dli_fname,"/tmp/hbl-x1d-combined/libhbl-af-only.so");
}
void status(const char *state) {
    QSaveFile f(QStringLiteral("/tmp/hbl-ui-af/ui.status"));
    if(f.open(QIODevice::WriteOnly)) {
        f.write(QByteArray(state)+" pid="+QByteArray::number(getpid())+"\n");f.commit();
    }
}
bool hash(const char *path,const char *expected) {
    QFile f(QString::fromLatin1(path));return f.open(QIODevice::ReadOnly) &&
        QCryptographicHash::hash(f.readAll(),QCryptographicHash::Sha256).toHex()==expected;
}
bool resourcesMatch() { for(const Entry &e:entries) if(!hash(e.path,e.sha)) return false;return true; }
}
extern "C" bool ui_af_register(int,const unsigned char *,const unsigned char *,const unsigned char *)
    __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool ui_af_register(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data) {
    using Function=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static void *symbol=dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_");
    auto next=reinterpret_cast<Function>(symbol);if(!next) return false;
    if(enabled() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !attempted) {
        attempted=true;
        if(afNext(symbol) && setting("HBL_AF_ONLY_ENABLE") && setting("HBL_AF_SETTINGS_ENABLE") && setting("HBL_AF_UI_R4_ENABLE") &&
           hash("/proc/self/exe","d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b") &&
           hash("/tmp/hbl-ui-af/ui-af.rcc",rccSha) && hash("/tmp/hbl-af-ui-r4/af-only-ui.rcc",afRccSha) &&
           hash("/tmp/hbl-x1d-combined/af-only-ui.rcc","dc63f7162f4794faca80b60b206ac1c17f58b3a402730ac5ab6e43a209be0040"))
            registered=QResource::registerResource(QStringLiteral("/tmp/hbl-ui-af/ui-af.rcc"));
    }
    // Qt5.5 注册顺序必须是本增量 -> 原 AF RCC -> 原厂；启动时另逐字核验结果。
    return next(version,tree,names,data);
}
extern "C" void ui_af_load(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void ui_af_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Function=void(*)(QQmlApplicationEngine *,const QUrl &);
    static void *symbol=dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl");
    auto next=reinterpret_cast<Function>(symbol);if(!next) { if(enabled()) status("ui-af-next-missing");return; }
    if(!enabled() || loaded) { next(engine,url);return; }
    loaded=true;
    if(!registered || !afNext(symbol)) { status("ui-af-chain-failed");return; }
    if(!resourcesMatch()) { status("ui-af-resource-hash-failed");return; }
    // AF-only 设置 hblAfInstall，AF-ui 设置 hblAf，最后进入真正的 Qt load。
    next(engine,url);
    if(engine->rootObjects().isEmpty()) { status("ui-af-root-failed");return; }
    QObject *af=engine->rootContext()->contextProperty(QStringLiteral("hblAf")).value<QObject*>();
    QObject *hold=engine->rootContext()->contextProperty(QStringLiteral("hblAfInstall")).value<QObject*>();
    if(!af || !hold || af==hold || af->parent()!=engine || hold->parent()!=engine ||
       !af->property("command").isValid() || !af->property("busy").isValid() ||
       hold->property("installationHold").type()!=QVariant::Bool || hold->property("installationHold").toBool()) {
        status("ui-af-context-failed");return;
    }
    for(const char *path:{"qrc:/mainmenu/ResidentLoader.qml","qrc:/settings/SettingsGeneric.qml","qrc:/mainmenu/Menu.qml",
        "qrc:/mainmenu/MainScreen.qml","qrc:/af-settings/SettingsPage.qml","qrc:/af-settings/AfSettingsHost.qml",
        "qrc:/af-settings/AfQuickEntry.qml","qrc:/controlscreen/ControlScreen.qml"}) {
        QQmlComponent c(engine,QUrl(QString::fromLatin1(path)));
        if(!c.isReady() || c.isError()) {
            std::fprintf(stderr,"UI AF component failed: %s\n",path);
            for(const QQmlError &e:c.errors()) std::fprintf(stderr,"%s\n",e.toString().toUtf8().constData());
            status("ui-af-component-failed");return;
        }
    }
    if(!resourcesMatch()) { status("ui-af-resource-changed");return; }
    status("ui-af-ready-resources10-components8-contexts2");
}
