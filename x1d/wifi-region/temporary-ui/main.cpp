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

static const QString dir=QStringLiteral("/run/hbl-hotspot-ui");
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
int main(int argc,char **argv) {
 if(argc==2 && !std::strcmp(argv[1],"--self-test"))
  return psk("password","IEEE")=="f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e"?0:1;
 umask(0077);QGuiApplication app(argc,argv);QQmlPropertyMap ui;
 ui.insert("status",QString::fromUtf8("临时联网测试：请先将无线模式设为关"));
 ui.insert("ssid","");ui.insert("password","");ui.insert("networks",QStringList());ui.insert("action","");ui.insert("busy",false);ui.insert("ready",false);
 QProcess worker;QTimer timer;bool started=false,starting=false,connecting=false,dhcp=false;int ticks=0,scanTicks=0;
 auto status=[&](const QString&s){ui.insert("status",s);};
 auto run=[&](const QString&arg){worker.start("/bin/sh",QStringList()<<dir+"/network.sh"<<arg);};
 QObject::connect(&worker,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),[&](QProcess::ProcessError){ui.insert("busy",false);status(QString::fromUtf8("临时辅助程序无法运行，请退出并恢复"));});
 QObject::connect(&worker,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),[&](int rc,QProcess::ExitStatus){
  worker.readAllStandardOutput();worker.readAllStandardError();ui.insert("busy",false);
  if(starting){starting=false;started=rc==0;ui.insert("ready",started);status(QString::fromUtf8(started?"已启用临时客户端，点击扫描热点":"启用失败：需原厂驱动、无线关闭且没有其他连接"));}
  else if(dhcp){dhcp=false;connecting=false;status(QString::fromUtf8(rc==0?"已连接并取得网络地址（互联网尚未验证）":"已关联热点，但获取网络地址失败"));}
 });
 QObject::connect(&ui,&QQmlPropertyMap::valueChanged,[&](const QString&key,const QVariant&value){
  if(key!="action")return;QString op=value.toString();ui.insert("action","");
  if(op=="close"){app.quit();return;}if(worker.state()!=QProcess::NotRunning)return;
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
 QObject::connect(&timer,&QTimer::timeout,[&](){
  if(!started||worker.state()!=QProcess::NotRunning)return;
  if(scanTicks>0&&--scanTicks==0){QStringList names;QList<QByteArray> lines=control("SCAN_RESULTS").split('\n');
   for(int i=1;i<lines.size();i++){QList<QByteArray> c=lines[i].split('\t');if(c.size()>=5&&!c[4].isEmpty()){QString n=QString::fromUtf8(c[4]);if(!names.contains(n))names<<n;}}
   ui.insert("networks",names);status(QString::fromUtf8("扫描完成，找到 %1 个热点；也可手动输入名称").arg(names.size()));
  }
  if(connecting){QByteArray s=control("STATUS");if(s.contains("wpa_state=COMPLETED")){dhcp=true;ui.insert("busy",true);status(QString::fromUtf8("热点已关联，正在获取网络地址"));run("dhcp");}
   else if(++ticks>=35){control("DISCONNECT");connecting=false;status(QString::fromUtf8("连接超时：检查热点名称、密码及最大兼容性"));}}
 });timer.start(1000);
 QQuickView view;view.rootContext()->setContextProperty("wifi",&ui);view.setResizeMode(QQuickView::SizeRootObjectToView);
 view.setSource(QUrl::fromLocalFile(dir+"/Main.qml"));if(view.status()==QQuickView::Error)return 2;
 view.showFullScreen();int rc=app.exec();timer.stop();
 if(worker.state()!=QProcess::NotRunning){worker.terminate();if(!worker.waitForFinished(3000)){worker.kill();worker.waitForFinished(1000);}}
 control("DISCONNECT");control("REMOVE_NETWORK all");
 QProcess restore;restore.start("/bin/sh",QStringList()<<dir+"/network.sh"<<"restore");
 if(!restore.waitForFinished(6000)||restore.exitCode()!=0)return 3;return rc;
}
