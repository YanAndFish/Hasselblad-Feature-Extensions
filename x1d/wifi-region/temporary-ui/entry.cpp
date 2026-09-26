#include <QtQuick/QQuickItem>
#include <QtGui/QGuiApplication>
#include <QtQuick/QQuickView>
#include <QtQml/QQmlContext>
#include <QtQml/QQmlPropertyMap>
#include <QtCore/QTimer>
#include <QtCore/QProcess>
#include <QtCore/QFile>
#include <QtCore/QCryptographicHash>
#include <QtCore/QDir>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <poll.h>
#include <unistd.h>
#include <cstring>
#include "jpeg_provider.h"
#include "focus_bridge.h"
#include "touch_bridge.h"
#include "flash_logic.h"
#include "page_pool_core.h"
#include "settings_rules_core.h"
#ifdef HBL_SEALED_UI
#include "sealed_resource.h"
#endif

static const QString dir=QStringLiteral("/run/hbl-hotspot-ui");
extern "C" __attribute__((visibility("hidden"))) int hbl_component_authorized(const char *directory);
static bool runtimeCopyMatches(const char *runtimeName,const char *signedName) {
 QFile live(dir+"/"+QString::fromLatin1(runtimeName));
 QFile original(QStringLiteral("/opt/hbl-af-only-v1/")+QString::fromLatin1(signedName));
 if(!live.open(QIODevice::ReadOnly) || !original.open(QIODevice::ReadOnly))return false;
 if(live.size()!=original.size() || live.size()>32*1024*1024)return false;
 QCryptographicHash a(QCryptographicHash::Sha256),b(QCryptographicHash::Sha256);
 return a.addData(&live) && b.addData(&original) && a.result()==b.result();
}
static bool componentAuthorized() {
 static const bool allowed=[](){
  if(hbl_component_authorized("/opt/hbl-af-only-v1")!=1)return false;
  const char *names[]={
#if !defined(HBL_SEALED_UI) && defined(HBL_EXPERIMENTAL_NETWORK)
   "Main.qml","Entry.qml",
#endif
#ifdef HBL_EXPERIMENTAL_NETWORK
   "network.sh","dhcp.sh",
#endif
   "radio-mode.sh"};
  if(!runtimeCopyMatches("flash-ui.rcc","af-ui.rcc"))return false;
  for(const char *name:names) {
   const QByteArray signedName=QByteArray("hotspot-")+name;
   if(!runtimeCopyMatches(name,signedName.constData()))return false;
  }
  return true;
 }();
 return allowed;
}
#ifdef HBL_EXPERIMENTAL_NETWORK
static QByteArray hmac(QByteArray k,const QByteArray &m) {
 if(k.size()>64) k=QCryptographicHash::hash(k,QCryptographicHash::Sha1);
 k=k.leftJustified(64,0);QByteArray a(64,0x36),b(64,0x5c);
 for(int i=0;i<64;i++){a[i]=a[i]^k[i];b[i]=b[i]^k[i];}
 return QCryptographicHash::hash(b+QCryptographicHash::hash(a+m,QCryptographicHash::Sha1),QCryptographicHash::Sha1);
}
static QByteArray psk(const QByteArray &password,const QByteArray &ssid) {
 QByteArray out;
 for(int n=1;n<=2;n++) {QByteArray s=ssid;s.append(char(0));s.append(char(0));s.append(char(0));s.append(char(n));
  QByteArray u=hmac(password,s),v=u;
  for(int j=1;j<4096;j++){u=hmac(password,u);for(int k=0;k<20;k++)v[k]=v[k]^u[k];}out+=v;
 }return out.left(32).toHex();
}
static QByteArray control(const QByteArray &command) {
 int fd=socket(AF_UNIX,SOCK_DGRAM,0);if(fd<0)return QByteArray();
 sockaddr_un local={},remote={};local.sun_family=remote.sun_family=AF_UNIX;
 QByteArray path=(dir+"/client.sock").toLocal8Bit();unlink(path.constData());
 std::strncpy(local.sun_path,path.constData(),sizeof(local.sun_path)-1);
 QByteArray target=(dir+"/ctrl/wlp1s0").toLocal8Bit();std::strncpy(remote.sun_path,target.constData(),sizeof(remote.sun_path)-1);
 QByteArray reply;
 if(bind(fd,reinterpret_cast<sockaddr*>(&local),sizeof(local))==0 && connect(fd,reinterpret_cast<sockaddr*>(&remote),sizeof(remote))==0 && send(fd,command.constData(),command.size(),0)==command.size()) {
  pollfd p={fd,POLLIN,0};if(poll(&p,1,400)>0){char b[32768];int n=recv(fd,b,sizeof(b),0);if(n>0)reply=QByteArray(b,n);}
 }close(fd);unlink(path.constData());return reply.trimmed();
}
#endif
#include <QtQml/QQmlApplicationEngine>
#include <QtQml/QQmlComponent>
#include <QtCore/QPointer>
#include <dlfcn.h>

// RAM-only resource replacement; original on-disk authorization and code stay intact.
extern "C" bool previewResource(const QString &,const QString &) __asm__("_ZN9QResource16registerResourceERK7QStringS2_");
extern "C" bool previewResource(const QString &file,const QString &root){
 using F=bool(*)(const QString&,const QString&);
 static F next=reinterpret_cast<F>(dlsym(RTLD_NEXT,"_ZN9QResource16registerResourceERK7QStringS2_"));
 if(!next)return false;
 if(file==QStringLiteral("/run/hbl-four-module/combined-ui.rcc") && componentAuthorized() && QFile::exists(dir+"/flash-ui.rcc")) {
#ifdef HBL_SEALED_UI
  return registerSealedResource(dir+"/flash-ui.rcc",root);
#else
  return next(dir+"/flash-ui.rcc",root);
#endif
 }
 return next(file,root);
}

extern "C" void previewStart(QProcess *,const QString &,const QStringList &,QIODevice::OpenMode) __asm__("_ZN8QProcess5startERK7QStringRK11QStringList6QFlagsIN9QIODevice12OpenModeFlagEE");
extern "C" void previewStart(QProcess *p,const QString &program,const QStringList &args,QIODevice::OpenMode mode){
 using F=void(*)(QProcess*,const QString&,const QStringList&,QIODevice::OpenMode);
 static F next=reinterpret_cast<F>(dlsym(RTLD_NEXT,"_ZN8QProcess5startERK7QStringRK11QStringList6QFlagsIN9QIODevice12OpenModeFlagEE"));
 if(!next)return;
 QStringList actual=args;
 if(program==QStringLiteral("/bin/sh") && actual.size()==2 && actual[0]==QStringLiteral("/opt/hbl-af-only-v1/radio-mode.sh") && componentAuthorized() && QFile::exists(dir+"/radio-mode.sh")) actual[0]=dir+"/radio-mode.sh";
 next(p,program,actual,mode);
}

#ifdef HBL_EXPERIMENTAL_NETWORK
static void note(const char *s){QFile f(dir+"/entry.status");if(f.open(QIODevice::WriteOnly))f.write(s);}
class Embedded:public QObject {
 QQmlPropertyMap ui;QProcess worker;QTimer timer,findPage;QQuickItem *panel=nullptr;
 QQmlContext *context=nullptr;QQmlEngine *engine=nullptr;
 bool started=false,starting=false,connecting=false,dhcp=false,restoring=false;int ticks=0,scanTicks=0;
 void status(const QString&s){ui.insert("status",s);}
 void run(const QString&a){worker.start("/bin/sh",QStringList()<<dir+"/network.sh"<<a);}
public:
 Embedded(QQmlEngine *e,QQuickItem *root):QObject(e),engine(e){
 ui.insert("status",QString::fromUtf8("临时联网测试：请先将无线模式设为关"));
 ui.insert("ssid","");ui.insert("password","");ui.insert("networks",QStringList());ui.insert("action","");ui.insert("busy",false);ui.insert("ready",false);



 QObject::connect(&worker,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),[this](QProcess::ProcessError){ui.insert("busy",false);status(QString::fromUtf8("临时辅助程序无法运行，请退出并恢复"));});
 QObject::connect(&worker,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),[this](int rc,QProcess::ExitStatus){
  worker.readAllStandardOutput();worker.readAllStandardError();ui.insert("busy",false);
  if(restoring){restoring=false;started=false;connecting=false;dhcp=false;ui.insert("ready",false);if(rc==0){panel->setVisible(false);timer.stop();}else status(QString::fromUtf8("退出恢复失败，请保持连接供诊断"));}
  else if(starting){starting=false;started=rc==0;ui.insert("ready",started);status(QString::fromUtf8(started?"已启用临时客户端，点击扫描热点":"启用失败：需原厂驱动、无线关闭且没有其他连接"));}
  else if(dhcp){dhcp=false;connecting=false;status(QString::fromUtf8(rc==0?"已连接并取得网络地址（互联网尚未验证）":"已关联热点，但获取网络地址失败"));}
 });
 QObject::connect(&ui,&QQmlPropertyMap::valueChanged,[this](const QString&key,const QVariant&value){
  if(key!="action")return;QString op=value.toString();ui.insert("action","");
  if(op=="back"){panel->setVisible(false);timer.stop();return;}
  if(op=="open"){panel->setVisible(true);timer.start();return;}
  if(worker.state()!=QProcess::NotRunning)return;
  if(op=="close"){control("DISCONNECT");control("REMOVE_NETWORK all");restoring=true;ui.insert("busy",true);run("restore");return;}
  if(op=="start"&&started){status(QString::fromUtf8("临时客户端已启用，可以扫描热点"));return;}
  if(op=="start"&&!started){starting=true;ui.insert("busy",true);status(QString::fromUtf8("正在启用临时无线客户端"));run("start");return;}
  if(!started)return;
  if(op=="scan") {bool ok=control("SCAN")=="OK";scanTicks=ok?3:0;status(QString::fromUtf8(ok?"正在扫描热点":"扫描请求失败"));}
  if(op=="connect") {
   QByteArray ssid=ui.value("ssid").toString().toUtf8(),pass=ui.value("password").toString().toUtf8();
   if(ssid.isEmpty()||ssid.size()>32||pass.size()<8||pass.size()>63){status(QString::fromUtf8("热点名须为1至32字节，密码须为8至63字节"));return;}
   control("DISCONNECT");control("REMOVE_NETWORK all");
   QByteArray id=control("ADD_NETWORK");bool valid=false;int number=id.toInt(&valid);
   if(!valid||number<0){status(QString::fromUtf8("创建临时网络失败"));return;}
   QByteArray prefix="SET_NETWORK "+id+" ";QByteArray secret=psk(pass,ssid);pass.fill(0);ui.insert("password","");
   bool ok=control(prefix+"ssid "+ssid.toHex())=="OK" && control(prefix+"psk "+secret)=="OK" && control(prefix+"key_mgmt WPA-PSK")=="OK" && control("SELECT_NETWORK "+id)=="OK";
   secret.fill(0);connecting=ok;ticks=0;status(QString::fromUtf8(ok?"正在连接热点，请保持手机热点页面打开":"提交连接配置失败"));
  }
 });
 QObject::connect(&timer,&QTimer::timeout,[this](){
  if(!panel || !panel->isVisible() || worker.state()!=QProcess::NotRunning)return;
  bool live=QFile::exists(dir+"/started") && control("PING")=="PONG";
  if(live!=started){started=live;ui.insert("ready",live);connecting=false;dhcp=false;status(QString::fromUtf8(live?"临时客户端已就绪，可以扫描热点":"临时客户端已停止，请点击启用"));}
  if(!started)return;
  if(!connecting && scanTicks==0 && QFile::exists(dir+"/bound")) status(QString::fromUtf8("已连接并取得网络地址（互联网尚未验证）"));
  if(scanTicks>0&&--scanTicks==0){QStringList names;QList<QByteArray> lines=control("SCAN_RESULTS").split('\n');
   for(int i=1;i<lines.size();i++){QList<QByteArray> c=lines[i].split('\t');if(c.size()>=5&&!c[4].isEmpty()){QString n=QString::fromUtf8(c[4]);if(!names.contains(n))names<<n;}}
   ui.insert("networks",names);status(QString::fromUtf8("扫描完成，找到 %1 个热点；也可手动输入名称").arg(names.size()));
  }
  if(connecting){QByteArray s=control("STATUS");if(s.contains("wpa_state=COMPLETED")){dhcp=true;ui.insert("busy",true);status(QString::fromUtf8("热点已关联，正在获取网络地址"));run("dhcp");}
   else if(++ticks>=35){control("DISCONNECT");connecting=false;status(QString::fromUtf8("连接超时：检查热点名称、密码及最大兼容性"));}}
 });timer.setInterval(1000);
 started=QFile::exists(dir+"/started") && QFile::exists(dir+"/ctrl/wlp1s0");ui.insert("ready",started);if(started)status(QString::fromUtf8("临时客户端已就绪，可以扫描热点"));

 context=new QQmlContext(e->rootContext(),this);context->setContextProperty("wifi",&ui);
#ifdef HBL_SEALED_UI
 QQmlComponent component(e,QUrl(QStringLiteral("qrc:///hblprotected/network/Main.qml")));
#else
 QQmlComponent component(e,QUrl::fromLocalFile(dir+"/Main.qml"));
#endif
 QObject *o=component.create(context);panel=qobject_cast<QQuickItem*>(o);
 if(!panel){note("panel-create-failed");return;}
 panel->setParent(root);panel->setParentItem(root);panel->setZ(100000);panel->setVisible(false);
 panel->setWidth(root->width());panel->setHeight(root->height());
 QObject::connect(root,&QQuickItem::widthChanged,[this,root](){panel->setWidth(root->width());});
 QObject::connect(root,&QQuickItem::heightChanged,[this,root](){panel->setHeight(root->height());});
 QObject::connect(&findPage,&QTimer::timeout,[this,root](){
  const QList<QObject*> items=root->findChildren<QObject*>();
  for(QObject *o:items){
   if(o->property("itemValues").toString()!=QStringLiteral("generalSettingsWiFi"))continue;
   QQuickItem *page=qobject_cast<QQuickItem*>(o);if(!page||!page->window())continue;
   QQuickItem *surface=page->window()->contentItem();panel->setParentItem(surface);panel->setWidth(surface->width());panel->setHeight(surface->height());
   if(page->findChild<QObject*>("temporaryHotspotEntry"))continue;
#ifdef HBL_SEALED_UI
   QQmlComponent button(engine,QUrl(QStringLiteral("qrc:///hblprotected/network/Entry.qml")));
#else
   QQmlComponent button(engine,QUrl::fromLocalFile(dir+"/Entry.qml"));
#endif
   QQuickItem *b=qobject_cast<QQuickItem*>(button.create(context));
   if(!b){note("entry-create-failed");return;}b->setParent(page);b->setParentItem(page);
   note("wifi-entry-attached");findPage.stop();break;
  }
 });findPage.start(1000);note("panel-created-waiting-wifi-page");
 }
};
#endif
extern "C" void load(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void load(QQmlApplicationEngine *e,const QUrl &u){
 using F=void(*)(QQmlApplicationEngine*,const QUrl&);static F next=reinterpret_cast<F>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
 if(!next)return;
 if(componentAuthorized() && !e->rootContext()->contextProperty("_hblFocusCore").isValid())
  e->rootContext()->setContextProperty("_hblFocusCore",new NativeFocusCore(e));
 if(componentAuthorized() && !e->rootContext()->contextProperty("_hblTouchCore").isValid())
  e->rootContext()->setContextProperty("_hblTouchCore",new NativeTouchCore(e));
 if(componentAuthorized() && !e->rootContext()->contextProperty("_hblFlashCore").isValid())
  e->rootContext()->setContextProperty("_hblFlashCore",new NativeFlashLogic(e));
 if(componentAuthorized() && !e->rootContext()->contextProperty("_hblPagePoolCore").isValid())
  e->rootContext()->setContextProperty("_hblPagePoolCore",new NativePagePoolCore(e));
 if(componentAuthorized() && !e->rootContext()->contextProperty("_hblSettingsRulesCore").isValid())
  e->rootContext()->setContextProperty("_hblSettingsRulesCore",new NativeSettingsRules(e));
 next(e,u);
#ifdef HBL_EXPERIMENTAL_NETWORK
 static bool done=false;if(done||e->rootObjects().isEmpty()||!componentAuthorized())return;
 QQuickItem *root=qobject_cast<QQuickItem*>(e->rootObjects().first());if(!root){note("root-not-item");return;}
 done=true;new Embedded(e,root);
#endif
}
