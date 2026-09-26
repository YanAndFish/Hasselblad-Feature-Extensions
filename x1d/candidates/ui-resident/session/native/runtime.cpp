// X1D 1.25.0 原厂 GUI 专用。只注册固定四资源，不实例化额外业务页面。
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
const char *root="/tmp/hbl-ui-resident";
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
    {":/mainmenu/ResidentLoader.qml","fa24ea45fafe6927b103e9225e6923de2164a8695f5ab9d4757ac7f3d657a64c"},
    {":/settings/SettingsGeneric.qml","fc6b8208c358dcdb685eda00d92d974e7219e801c4cac89c1ffb79be968f8955"},
    {":/mainmenu/Menu.qml","593344a502e333f24abefd30d28cac040c9c1b5d5be31814cb34292fd54c7961"},
    {":/mainmenu/MainScreen.qml","552d546a679071669eb67b7cb02f4424c3c56ed020beaa00244bc7ae5f435433"}
};
}
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
           hash("/tmp/hbl-ui-resident/ui-resident.rcc","0456d37bc5ddbc57b97e8a9e8cc41b3eff0bd5efa192215bd9f3ae6022029994"))
            registered=QResource::registerResource(QStringLiteral("/tmp/hbl-ui-resident/ui-resident.rcc"));
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
    original(engine,url);
    if(engine->rootObjects().isEmpty()) { status("ui-resident-root-failed");return; }
    for(const Entry &e:entries) {
        QQmlComponent c(engine,QUrl(QStringLiteral("qrc")+QString::fromLatin1(e.path)));
        if(!c.isReady() || c.isError()) {
            std::fprintf(stderr,"UI resident component failed: %s\n",e.path);
            for(const QQmlError &error:c.errors()) std::fprintf(stderr,"%s\n",error.toString().toUtf8().constData());
            status("ui-resident-component-failed");return;
        }
    }
    status("ui-resident-ready-resources4-components4");
}
