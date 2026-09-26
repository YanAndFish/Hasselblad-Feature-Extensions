// Independent AF startup UI: no replay, page prewarming, flash or radio client.
#include "formal_install_hold.h"
#include <QtCore/qfile.h>
#include <QtCore/qtimer.h>
#include <QtCore/qresource.h>
#include <QtCore/qsavefile.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlpropertymap.h>
#include <dlfcn.h>
#include <cstdlib>
namespace {
bool requested(){const char *s=std::getenv("HBL_AF_ONLY_BOOT");return s && !strcmp(s,"1");}
bool overlay=false;
void report(const QByteArray &s){QSaveFile f(QStringLiteral("/run/hbl-four-module/af-ui.status"));if(f.open(QIODevice::WriteOnly)){f.write(s+" uptimeMs="+QByteArray::number(static_cast<qulonglong>(holdNow()))+" pid="+QByteArray::number(getpid())+"\n");f.commit();}}
class Minimal : public QQmlPropertyMap {
 uint64_t deadline;QTimer timer;bool finished=false;
public:
 explicit Minimal(QQmlApplicationEngine *e):QQmlPropertyMap(e),deadline(holdReadDeadline()) {
  insert("bootLoading",true);insert("bootFailed",false);insert("bootProgress",QString::fromUtf8("正在装载对焦…"));
  insert("installationHold",holdWindow(holdNow(),deadline));insert("installPulse",false);
  QObject::connect(this,&QQmlPropertyMap::valueChanged,this,[this](const QString &key,const QVariant &v){
   if(key=="installPulse" && v.toBool() && !finished && holdWindow(holdNow(),deadline) && !holdReleased())
    if(!holdAtomicPulse(getpid(),deadline,holdNow()))fail();
   if(key=="installPulse")insert("installPulse",false);
  });
  timer.setInterval(250);QObject::connect(&timer,&QTimer::timeout,this,[this](){
   if(finished)return;
   if(QFile::exists(QStringLiteral("/run/hbl-four-module/boot-failed"))){fail();return;}
   QFile f(QStringLiteral("/run/hbl-four-module/boot-loader.status"));
   QByteArray s;if(f.open(QIODevice::ReadOnly))s=f.read(512);
   if(s.startsWith("state=ready phase=af-ready ")){
    finished=true;insert("installationHold",false);insert("bootLoading",false);report("af-ui-released");
   }else if(s.startsWith("state=failed") || s.startsWith("state=blocked") || !holdWindow(holdNow(),deadline))fail();
  });timer.start();
 }
 void fail(){finished=true;insert("installationHold",false);insert("bootFailed",true);report("af-ui-failed");}
};
Minimal *runtime=nullptr;
}
extern "C" bool afRegister(int,const unsigned char*,const unsigned char*,const unsigned char*) __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool afRegister(int v,const unsigned char*t,const unsigned char*n,const unsigned char*d){
 using Fn=bool(*)(int,const unsigned char*,const unsigned char*,const unsigned char*);
 static Fn fn=reinterpret_cast<Fn>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));if(!fn)return false;
 if(requested() && v==1 && reinterpret_cast<quintptr>(t)==0x1ec7f0 && !overlay)overlay=QResource::registerResource(QStringLiteral("/run/hbl-four-module/af-ui.rcc"));
 return fn(v,t,n,d);
}
extern "C" void afLoad(QQmlApplicationEngine*,const QUrl&) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void afLoad(QQmlApplicationEngine*e,const QUrl&u){
 using Fn=void(*)(QQmlApplicationEngine*,const QUrl&);static Fn fn=reinterpret_cast<Fn>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));if(!fn)return;
 if(requested() && overlay && !runtime){runtime=new Minimal(e);e->rootContext()->setContextProperty("hblNative",runtime);}
 fn(e,u);if(requested())report(overlay && runtime && !e->rootObjects().isEmpty()?"af-ui-created":"af-ui-unavailable");
}
