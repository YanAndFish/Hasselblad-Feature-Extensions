#include <QtCore/qcoreapplication.h>
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qjsondocument.h>
#include <QtCore/qjsonobject.h>
#include <QtCore/qresource.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qtimer.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlpropertymap.h>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <dlfcn.h>
#include <time.h>
extern "C" {
#include "settings_wire.h"
}
#include "settings_socket.h"
namespace {
bool enabled(){const char *v=std::getenv("HBL_AF_SETTINGS_ENABLE");return v && !std::strcmp(v,"1");}
bool number(const QJsonObject &o,const char *key,u32 *out){
    QJsonValue v=o.value(QString::fromLatin1(key));if(!v.isDouble())return false;
    double x=v.toDouble();if(!std::isfinite(x) || x<0 || x>0x7fffffff || std::floor(x)!=x)return false;
    *out=u32(x);return true;
}
class Settings:public QQmlPropertyMap {
public:
    explicit Settings(QQmlApplicationEngine *engine):QQmlPropertyMap(engine){
        insert("command",QString());insert("connected",false);insert("busy",false);insert("fastAdvanceAvailable",false);insert("fineAdvanceAvailable",false);
        insert("statusText",QStringLiteral("打开页面后读取相机配置"));insert("revision",0);insert("activeRevision",0);insert("generation",0);
        insert("probe",0);insert("fast",0);insert("fine",0);insert("newDirection",false);insert("fastAdvanceMs",65534);insert("fineAdvanceMs",65534);
        /* 目前没有已验证的毫秒预设；切档不能伪造默认估计，也不保留上档手调值。 */
        insert("fastPresets",QVariantList{65535,65535,65535,65535});insert("finePresets",QVariantList{65535,65535,65535,65535,65535});
        insert("activeProbe",0);insert("activeFast",0);insert("activeFine",0);insert("activeNewDirection",false);insert("activeFastAdvanceMs",0);insert("activeFineAdvanceMs",0);
        timespec now={};clock_gettime(CLOCK_MONOTONIC,&now);session=u32(now.tv_nsec)^u32(now.tv_sec)^u32(getpid());if(!session)session=1;
        fd=as_bind(AS_UI);elapsed.start();
        if(fd<0){insert("statusText",QStringLiteral("AF 配置接口未就绪"));return;}
        auto notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int){receive();});
        timer.setInterval(250);QObject::connect(&timer,&QTimer::timeout,this,[this](){
            if(pending && elapsed.elapsed()-sentAt>2200){pending=false;insert("busy",false);insert("connected",false);insert("statusText",QStringLiteral("未收到确认；需重新读取，不能视为已应用"));}
            if(shown && !pending && elapsed.elapsed()-lastQuery>=1000)query();
        });timer.start();
    }
    ~Settings() override{if(fd>=0){close(fd);unlink(AS_UI);}}
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override{
        if(key!="command")return value(key);
        QByteArray bytes=input.toString().toUtf8();if(bytes.size()>512)return QString();
        QJsonParseError error;auto doc=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !doc.isObject())return QString();
        auto o=doc.object();auto op=o.value("op").toString();
        if(op=="visible" && o.size()==2 && o.value("value").isBool()){
            shown=o.value("value").toBool();if(shown && !pending)query();
        }else if(op=="read" && o.size()==1 && !pending)query();
        else if(op=="apply" && o.size()==7 && !pending && value("connected").toBool()){
            NaConfig c={};c.magic=NA_CONFIG_MAGIC;c.abi=NA_CONFIG_ABI;c.lens=75;c.revision=confirmed.revision+1;
            if(!number(o,"probe",&c.probe) || !number(o,"fast",&c.fast) || !number(o,"fine",&c.fine) ||
               !number(o,"fastAdvanceMs",&c.fast_advance_ms) || !number(o,"fineAdvanceMs",&c.fine_advance_ms) ||
               !o.value("newDirection").isBool())return QString();
            c.flags=(confirmed.flags&NA_FAR_FIRST)|(o.value("newDirection").toBool()?NA_NEW_DIRECTION:0);c.checksum=na_config_checksum(&c);
            if(na_config_validate(&c))return QString();send(AS_APPLY,&c);
        }
        return QString();
    }
private:
    int fd=-1;bool shown=false,pending=false;u32 session=0,sequence=0,operation=0;
    QElapsedTimer elapsed;QTimer timer;qint64 sentAt=0,lastQuery=-1000;NaConfig confirmed={};
    void query(){lastQuery=elapsed.elapsed();send(AS_QUERY,nullptr);}
    void send(u32 op,const NaConfig *c){
        if(fd<0 || sequence>=0x7fffffff)return;
        unsigned char p[255]={};as_put(p,0x414c4248);as_put(p+4,0x21335346);as_put(p+8,3);as_put(p+12,op);
        as_put(p+16,session);as_put(p+20,++sequence);if(c){as_put(p+24,confirmed.revision);as_config_write(p+28,c);}
        as_put(p+251,as_hash(p,251));operation=op;sentAt=elapsed.elapsed();pending=as_send(fd,AS_BACKEND,p);
        insert("busy",pending);if(!pending){insert("connected",false);insert("statusText",QStringLiteral("AF 配置接口不可达"));}
    }
    void publish(const NaConfig &c,const NaConfig &a,u32 generation){
        confirmed=c;insert("revision",int(c.revision));insert("activeRevision",int(a.revision));insert("generation",int(generation));
        insert("probe",int(c.probe));insert("fast",int(c.fast));insert("fine",int(c.fine));insert("newDirection",bool(c.flags&NA_NEW_DIRECTION));insert("fastAdvanceMs",int(c.fast_advance_ms));insert("fineAdvanceMs",int(c.fine_advance_ms));
        insert("activeProbe",int(a.probe));insert("activeFast",int(a.fast));insert("activeFine",int(a.fine));insert("activeNewDirection",bool(a.flags&NA_NEW_DIRECTION));insert("activeFastAdvanceMs",int(a.fast_advance_ms));insert("activeFineAdvanceMs",int(a.fine_advance_ms));
    }
    void receive(){
        for(unsigned count=0;count<4;count++){
            unsigned char p[255];int result=as_recv(fd,p,AS_BACKEND);if(result<0)return;if(!result || !pending)continue;
            if(!as_reply(p) || as_get(p+8)!=3 || as_get(p+12)!=(operation|0x80000000u) ||
               as_get(p+16)!=session || as_get(p+20)!=sequence || as_get(p+251)!=as_hash(p,251) || elapsed.elapsed()-sentAt>2200)continue;
            NaConfig c,a;as_config_read(&c,p+44);as_config_read(&a,p+88);u32 status=as_get(p+24);
            pending=false;insert("busy",false);
            if(na_config_validate(&c) || na_config_validate(&a) || as_get(p+36)!=18){
                insert("connected",false);insert("statusText",QStringLiteral("配置或镜头身份校验失败"));continue;
            }
            publish(c,a,as_get(p+28));insert("connected",true);insert("fastAdvanceAvailable",bool(as_get(p+40)&1));insert("fineAdvanceAvailable",bool(as_get(p+40)&2));
            if(status)insert("statusText",QStringLiteral("配置未应用，错误码 %1；已重新读取当前值").arg(status));
            else insert("statusText",c.revision==a.revision?QStringLiteral("已读取本轮配置"):QStringLiteral("已确认保存，下轮 AF 生效"));
        }
    }
};
Settings *settings=nullptr;
}
extern "C" void as_load(QQmlApplicationEngine *,const QUrl &) asm("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void as_load(QQmlApplicationEngine *engine,const QUrl &url){
    using Load=void (*)(QQmlApplicationEngine *,const QUrl &);
    static auto next=reinterpret_cast<Load>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!next)return;
    /* 最终组合资源由主任务唯一注册；本库只提供上下文对象，不替换 RCC。 */
    if(enabled() && !settings){
        settings=new Settings(engine);engine->rootContext()->setContextProperty(QStringLiteral("hblAf"),settings);
        QObject::connect(settings,&QObject::destroyed,[](){settings=nullptr;});
    }
    next(engine,url);
}
