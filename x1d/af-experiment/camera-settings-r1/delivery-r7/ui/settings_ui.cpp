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
#include <cstdio>
#include <fcntl.h>
extern "C" {
#include "settings_wire.h"
}
#include "settings_socket.h"
#include "ui_flow.h"
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
        insert("command",QString());insert("connected",false);insert("busy",false);insert("reading",false);insert("applying",false);insert("canApply",false);insert("fastAdvanceAvailable",false);insert("fineAdvanceAvailable",false);
        insert("statusText",QStringLiteral("打开页面后读取相机配置"));insert("revision",0);insert("activeRevision",0);insert("generation",0);
        insert("startSpeed",0);insert("startSamples",3);insert("activeStartSpeed",0);insert("activeStartSamples",3);insert("probe",0);insert("fast",0);insert("fine",0);insert("newDirection",false);insert("fastAdvanceMs",65534);insert("fineAdvanceMs",65534);
        /* 目前没有已验证的毫秒预设；切档不能伪造默认估计，也不保留上档手调值。 */
        insert("fastPresets",QVariantList{65535,65535,65535,65535});insert("finePresets",QVariantList{65535,65535,65535,65535,65535});
        insert("activeProbe",0);insert("activeFast",0);insert("activeFine",0);insert("activeNewDirection",false);insert("activeFastAdvanceMs",0);insert("activeFineAdvanceMs",0);
        timespec now={};clock_gettime(CLOCK_MONOTONIC,&now);session=u32(now.tv_nsec)^u32(now.tv_sec)^u32(getpid());if(!session)session=1;
        fd=as_bind(AS_UI);elapsed.start();
        if(fd<0){insert("statusText",QStringLiteral("AF 配置接口未就绪；本地仍可编辑"));updateState("bind-failed");return;}
        auto notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int){receive();});
        timer.setInterval(250);QObject::connect(&timer,&QTimer::timeout,this,[this](){
            bool wasApply=flow.operation==AS_APPLY;bool wasQueued=flow.queued;
            if(flow.timeout(elapsed.elapsed())){
                ++timeouts;insert("connected",false);
                insert("statusText",wasApply?QStringLiteral("保存结果未确认；先重新读取，勿重复保存"):(wasQueued?QStringLiteral("读取超时，保存未发送；请重新读取"):QStringLiteral("读取超时；本地修改保留，可重新读取")));
                updateState("timeout");return;
            }
            if(flow.automatic(elapsed.elapsed()))query();
        });timer.start();updateState("ready");
    }
    ~Settings() override{if(fd>=0){close(fd);unlink(AS_UI);}}
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override{
        if(key!="command")return value(key);
        QByteArray bytes=input.toString().toUtf8();if(bytes.size()>512)return QString();
        QJsonParseError error;auto doc=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !doc.isObject())return QString();
        auto o=doc.object();auto op=o.value("op").toString();
        if(op=="visible" && (o.size()==2 || o.size()==4) && o.value("value").isBool()){
            if(o.size()==4){u32 w=0,h=0;if(!number(o,"width",&w) || !number(o,"height",&h) || w>4096 || h>4096)return QString();width=w;height=h;}
            bool entered=!flow.shown && o.value("value").toBool();flow.shown=o.value("value").toBool();
            if(entered && !flow.pending() && !flow.paused)query();
            updateState("visible");
        }else if(op=="localEdit" && o.size()==1){++localEdits;updateState("local-edit");}
        else if(op=="read" && o.size()==1 && !flow.applying()){
            if(!flow.pending()){flow.paused=false;query();}
        }else if(op=="apply" && o.size()==10 && !flow.applying() && !flow.paused && value("connected").toBool()){
            u32 expected=0;if(!number(o,"expectedRevision",&expected) || expected!=confirmed.revision){
                insert("statusText",QStringLiteral("配置版本已变化；请重新读取后编辑"));updateState("draft-conflict");return QString();
            }
            NaConfig c={};c.magic=NA_CONFIG_MAGIC;c.abi=NA_CONFIG_ABI;c.lens=75;c.revision=expected+1;
            if(!number(o,"startSpeed",&c.start_speed) || !number(o,"startSamples",&c.start_samples) || !number(o,"probe",&c.probe) || !number(o,"fast",&c.fast) || !number(o,"fine",&c.fine) ||
               !number(o,"fastAdvanceMs",&c.fast_advance_ms) || !number(o,"fineAdvanceMs",&c.fine_advance_ms) ||
               (!o.value("newDirection").isBool() || o.value("newDirection").toBool()))return QString();
            c.flags=confirmed.flags&NA_FAR_FIRST;c.checksum=na_config_checksum(&c);
            if(na_config_validate(&c))return QString();
            submitted=c;expectedRevision=expected;
            if(flow.reading()){
                flow.queued=true;insert("statusText",QStringLiteral("读取完成后核对版本并保存"));updateState("apply-queued");
            }else send(AS_APPLY,&submitted);
        }
        return QString();
    }
private:
    int fd=-1;UiFlow flow;u32 session=0,sequence=0,expectedRevision=0;
    QElapsedTimer elapsed;QTimer timer;NaConfig confirmed={},submitted={};
    u32 queries=0,applies=0,replies=0,rejectedEnvelope=0,rejectedConfig=0,rejectedLens=0,rejectedSocket=0,timeouts=0,sendFailures=0,localEdits=0,width=0,height=0;
    void updateState(const char *stage){
        insert("reading",flow.reading());insert("applying",flow.applying());insert("busy",flow.applying());insert("canApply",value("connected").toBool() && !flow.paused && !flow.applying());
        int saved=errno;const char *path=AS_DIRECTORY "/ui-r4.status";uint32_t mode=0,uid=0;
        if(as_directory()){
            int state=as_stat(path,mode,uid);
            if((state && errno==ENOENT) || (!state && S_ISREG(mode) && uid==geteuid() && (mode&0777)==0600)){
                int file=open(path,O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600);
                if(file>=0){char text[512];int n=std::snprintf(text,sizeof(text),
                    "stage=%s pid=%u bound=%u shown=%u width=%u height=%u connected=%u reading=%u applying=%u paused=%u queries=%u applies=%u replies=%u envelope=%u config=%u lens=%u socket=%u timeouts=%u sendfail=%u edits=%u\n",
                    stage,unsigned(getpid()),unsigned(fd>=0),unsigned(flow.shown),width,height,unsigned(value("connected").toBool()),unsigned(flow.reading()),unsigned(flow.applying()),unsigned(flow.paused),queries,applies,replies,rejectedEnvelope,rejectedConfig,rejectedLens,rejectedSocket,timeouts,sendFailures,localEdits);
                    if(n>0 && n<int(sizeof(text)))(void)write(file,text,size_t(n));close(file);}
            }
        }
        errno=saved;
    }
    void query(){if(flow.pending() || flow.applying())return;send(AS_QUERY,nullptr);}
    void send(u32 op,const NaConfig *c){
        if(fd<0 || sequence>=0x7fffffff){flow.failed();insert("connected",false);updateState("unavailable");return;}
        unsigned char p[255]={};as_put(p,0x414c4248);as_put(p+4,0x21345346);as_put(p+8,NA_CONFIG_ABI);as_put(p+12,op);
        as_put(p+16,session);as_put(p+20,++sequence);if(c){as_put(p+24,expectedRevision);as_config_write(p+28,c);}
        as_put(p+251,as_hash(p,251));flow.begin(op,elapsed.elapsed());
        if(op==AS_QUERY)++queries;else ++applies;
        if(!as_send(fd,AS_BACKEND,p)){
            ++sendFailures;flow.failed();insert("connected",false);insert("statusText",QStringLiteral("AF 配置接口不可达；本地仍可编辑"));updateState("send-failed");return;
        }
        insert("statusText",op==AS_APPLY?QStringLiteral("等待相机确认保存"):QStringLiteral("正在读取；可继续编辑"));updateState(op==AS_APPLY?"apply-sent":"query-sent");
    }
    void publish(const NaConfig &c,const NaConfig &a,u32 generation){
        confirmed=c;insert("revision",int(c.revision));insert("activeRevision",int(a.revision));insert("generation",int(generation));
        insert("startSpeed",int(c.start_speed));insert("startSamples",int(c.start_samples));insert("activeStartSpeed",int(a.start_speed));insert("activeStartSamples",int(a.start_samples));insert("probe",int(c.probe));insert("fast",int(c.fast));insert("fine",int(c.fine));insert("newDirection",false);insert("fastAdvanceMs",int(c.fast_advance_ms));insert("fineAdvanceMs",int(c.fine_advance_ms));
        insert("activeProbe",int(a.probe));insert("activeFast",int(a.fast));insert("activeFine",int(a.fine));insert("activeNewDirection",false);insert("activeFastAdvanceMs",int(a.fast_advance_ms));insert("activeFineAdvanceMs",int(a.fine_advance_ms));
    }
    void receive(){
        for(unsigned count=0;count<4;count++){
            unsigned char p[255];int result=as_recv(fd,p,AS_BACKEND);if(result<0)return;
            if(!result){++rejectedSocket;updateState("socket-rejected");continue;}
            if(!flow.pending()){++rejectedEnvelope;updateState("unsolicited");continue;}
            NaConfig c,a;u32 status=0;bool wasApply=flow.operation==AS_APPLY;
            int error=uiReply(p,flow,session,sequence,elapsed.elapsed(),submitted,c,a,status);
            if(error==UI_ENVELOPE){++rejectedEnvelope;updateState("envelope-rejected");continue;}
            flow.completed();
            if(error){
                flow.failed();insert("connected",false);
                if(error==UI_LENS){++rejectedLens;insert("statusText",QStringLiteral("镜头身份校验失败；本地修改保留"));updateState("lens-rejected");}
                else if(error==UI_APPLY_MISMATCH){++rejectedConfig;insert("statusText",QStringLiteral("保存回复与提交内容不符；需重新读取"));updateState("apply-mismatch");}
                else {++rejectedConfig;insert("statusText",QStringLiteral("配置校验失败；本地修改保留"));updateState("config-rejected");}
                continue;
            }
            ++replies;publish(c,a,as_get(p+28));insert("connected",true);insert("fastAdvanceAvailable",bool(as_get(p+40)&1));insert("fineAdvanceAvailable",bool(as_get(p+40)&2));
            if(status){flow.queued=false;flow.paused=true;insert("statusText",QStringLiteral("配置未应用，错误码 %1；请核对后重新读取").arg(status));updateState("remote-error");continue;}
            if(flow.queued){
                flow.queued=false;
                if(c.revision!=expectedRevision){insert("statusText",QStringLiteral("配置版本已变化；请重新读取后编辑"));updateState("queued-conflict");continue;}
                send(AS_APPLY,&submitted);continue;
            }
            insert("statusText",c.revision==a.revision?QStringLiteral("已读取本轮配置"):QStringLiteral("已确认保存，下轮 AF 生效"));updateState(wasApply?"apply-confirmed":"query-confirmed");
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

/* Keep the frozen AF-only resource/hold library; redirect only its fixed RCC file. */
extern "C" bool af_r4_resource(const QString &,const QString &) asm("_ZN9QResource16registerResourceERK7QStringS2_");
extern "C" bool af_r4_resource(const QString &file,const QString &root){
    using Register=bool (*)(const QString &,const QString &);
    static auto next=reinterpret_cast<Register>(dlsym(RTLD_NEXT,"_ZN9QResource16registerResourceERK7QStringS2_"));
    if(!next)return false;
    const char *v=std::getenv("HBL_AF_UI_R4_ENABLE");
    if(v && !std::strcmp(v,"1") && file==QStringLiteral("/tmp/hbl-x1d-combined/af-only-ui.rcc"))
        return next(QStringLiteral("/tmp/hbl-af-ui-r4/af-only-ui.rcc"),root);
    return next(file,root);
}
