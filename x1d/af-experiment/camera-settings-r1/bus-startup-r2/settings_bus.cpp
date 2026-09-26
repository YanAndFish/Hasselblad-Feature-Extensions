/* 复用原厂 MessageIO 对象；没有串口、USB、客户端注册或自动设备查询。 */
#include <QtCore/qbytearray.h>
#include <QtCore/qmetaobject.h>
#include <QtCore/qpointer.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qthread.h>
#include <QtCore/qtimer.h>
#include <QtCore/qelapsedtimer.h>
#include <dlfcn.h>
#include <cstdlib>
#include <cstdio>
#include <fcntl.h>
#include <cstddef>
extern "C" {
#include "settings_wire.h"
}
#include "settings_socket.h"
static_assert(QT_VERSION==0x050501 && sizeof(void *)==4 && sizeof(QByteArray)==4,"Fixed ARM Qt ABI");
namespace {
using Activate=void (*)(QObject *,const QMetaObject *,int,void **);
Activate nextActivate=nullptr;const QMetaObject *messageMeta=nullptr,*uartMeta=nullptr;
using Connect=QMetaObject::Connection (*)(const QObject *,void **,const QObject *,void **,
    QtPrivate::QSlotObjectBase *,Qt::ConnectionType,const int *,const QMetaObject *);
Connect nextConnect=nullptr;
const QMetaObject *resolveMeta(const char *name,const QMetaObject **slot){
    auto *p=__atomic_load_n(slot,__ATOMIC_ACQUIRE);if(p)return p;
    p=reinterpret_cast<const QMetaObject *>(dlsym(RTLD_DEFAULT,name));
    if(p)__atomic_store_n(slot,p,__ATOMIC_RELEASE);return p;
}
void resolveMetas(){
    resolveMeta("_ZN19MessageIO_Interface16staticMetaObjectE",&messageMeta);
    resolveMeta("_ZN14MessageIO_UART16staticMetaObjectE",&uartMeta);
}
void health(const char *stage,int error=0){
    const int saved=errno;
    if(as_directory()){
        const char *path=AS_DIRECTORY "/backend-r2.status";uint32_t mode=0,uid=0;
        const int statResult=as_stat(path,mode,uid);
        if((statResult && errno==ENOENT) || (!statResult && S_ISREG(mode) && uid==geteuid() && (mode&0777)==0600)){
            int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600);
            if(fd>=0){char text[160];int n=std::snprintf(text,sizeof(text),"stage=%s error=%d meta=%u uart=%u\n",stage,error,
                unsigned(__atomic_load_n(&messageMeta,__ATOMIC_ACQUIRE)!=nullptr),unsigned(__atomic_load_n(&uartMeta,__ATOMIC_ACQUIRE)!=nullptr));
                if(n>0 && n<int(sizeof(text)))(void)write(fd,text,size_t(n));close(fd);}
        }
    }
    errno=saved;
}
Connect resolveConnect(){
    Connect f=__atomic_load_n(&nextConnect,__ATOMIC_ACQUIRE);if(f)return f;
    f=reinterpret_cast<Connect>(dlsym(RTLD_NEXT,"_ZN7QObject11connectImplEPKS_PPvS1_S3_PN9QtPrivate15QSlotObjectBaseEN2Qt14ConnectionTypeEPKiPK11QMetaObject"));
    if(!f)_exit(78);__atomic_store_n(&nextConnect,f,__ATOMIC_RELEASE);return f;
}
bool ownerMatches(const QObject *object){
    auto *uart=__atomic_load_n(&uartMeta,__ATOMIC_ACQUIRE);
    return object && uart && object->metaObject()==uart;
}
QObject *scheduledOwner=nullptr;
bool enabled(){const char *p=std::getenv("HBL_AF_SETTINGS_ENABLE");return p && !std::strcmp(p,"1");}
Activate resolve(){
    Activate f=__atomic_load_n(&nextActivate,__ATOMIC_ACQUIRE);if(f)return f;
    f=reinterpret_cast<Activate>(dlsym(RTLD_NEXT,"_ZN11QMetaObject8activateEP7QObjectPKS_iPPv"));
    if(!f)_exit(78);__atomic_store_n(&nextActivate,f,__ATOMIC_RELEASE);return f;
}
class Bus:public QObject {
public:
    explicit Bus(QObject *owner):QObject(owner),io(owner){
        health("binding");fd=as_bind(AS_BACKEND);if(fd<0){health("bind-failed",errno);return;}
        auto notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int){receive();});clock.start();health("ready");
    }
    ~Bus() override{if(fd>=0){close(fd);unlink(AS_BACKEND);}}
    static Bus *find(QObject *owner){
        /* 只在 owner 线程读取其子对象；其他 MessageIO 对象不共享裸 Bus 指针。 */
        for(QObject *child:owner->children())if(auto *found=dynamic_cast<Bus *>(child))return found;
        return nullptr;
    }
    void reply(const QByteArray &data){
        if(!pending || data.size()!=259 || clock.elapsed()-sentAt>2000)return;
        const auto *p=reinterpret_cast<const unsigned char *>(data.constData());
        if(p[0]!=0x10 || p[1]!=3 || p[2]!=1 || p[3]!=5 || !as_reply(p+4) ||
           as_get(p+12)!=3 || as_get(p+20)!=session || as_get(p+24)!=sequence ||
           as_get(p+16)!=(operation|0x80000000u) || as_get(p+255)!=as_hash(p+4,251))return;
        pending=false;as_send(fd,AS_UI,p+4);
    }
private:
    QPointer<QObject> io;int fd=-1;QElapsedTimer clock;bool pending=false;qint64 sentAt=0;
    u32 session=0,sequence=0,operation=0;
    void receive(){
        /* 一次事件最多处理四包，避免 UI 请求占满原厂消息线程。 */
        for(unsigned count=0;count<4;count++){
            unsigned char p[255];int result=as_recv(fd,p,AS_UI);if(result<0)return;if(!result)continue;
            if(!io || QThread::currentThread()!=io->thread() || !as_owned(p) || as_get(p+8)!=3 ||
               !as_get(p+16) || !as_get(p+20) || as_get(p+251)!=as_hash(p,251))continue;
            u32 op=as_get(p+12);if(op!=AS_QUERY && op!=AS_APPLY)continue;
            bool valid=true;for(u32 i=72;i<251;i++)if(p[i])valid=false;
            if(op==AS_QUERY){for(u32 i=24;i<72;i++)if(p[i])valid=false;}
            else {NaConfig c;as_config_read(&c,p+28);if(na_config_validate(&c) || c.revision!=as_get(p+24)+1)valid=false;}
            if(!valid || (pending && clock.elapsed()-sentAt<=2000))continue;
            QByteArray packet(261,'\0');packet[0]=0x0f;packet[1]=3;packet[2]=5;packet[3]=1;packet[5]=char(255);
            std::memcpy(packet.data()+6,p,255);session=as_get(p+16);sequence=as_get(p+20);operation=op;sentAt=clock.elapsed();pending=true;
            if(!QMetaObject::invokeMethod(io,"SendMessage",Qt::DirectConnection,Q_ARG(QByteArray,packet)))pending=false;
        }
    }
};
void discover(QObject *sender){
    if(!ownerMatches(sender))return;
    QObject *expected=nullptr;
    if(!__atomic_compare_exchange_n(&scheduledOwner,&expected,sender,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    health("owner-found");
    QObject::connect(sender,&QObject::destroyed,[](QObject *object){
        QObject *expectedOwner=object;
        if(__atomic_compare_exchange_n(&scheduledOwner,&expectedOwner,nullptr,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))health("owner-destroyed");
    });
    health("queued");
    QTimer::singleShot(0,sender,[sender](){
        if(QThread::currentThread()!=sender->thread()){health("wrong-thread");return;}
        if(Bus::find(sender))return;
        if(!ownerMatches(sender) || sender->metaObject()->indexOfSlot("SendMessage(QByteArray)")<0){health("slot-missing");return;}
        new Bus(sender);
    });
}
}
__attribute__((constructor)) static void setup(){
    resolve();resolveConnect();resolveMetas();health(enabled()?"loaded":"disabled");
}
QMetaObject::Connection af_connect(const QObject *,void **,const QObject *,void **,
    QtPrivate::QSlotObjectBase *,Qt::ConnectionType,const int *,const QMetaObject *)
    asm("_ZN7QObject11connectImplEPKS_PPvS1_S3_PN9QtPrivate15QSlotObjectBaseEN2Qt14ConnectionTypeEPKiPK11QMetaObject");
QMetaObject::Connection af_connect(const QObject *sender,void **signal,const QObject *receiver,void **slot,
    QtPrivate::QSlotObjectBase *functor,Qt::ConnectionType type,const int *types,const QMetaObject *meta){
    const int incoming=errno;Connect next=resolveConnect();
    if(enabled())resolveMetas();
    QObject *candidate=enabled()?(ownerMatches(receiver)?const_cast<QObject *>(receiver):
        (ownerMatches(sender)?const_cast<QObject *>(sender):nullptr)):nullptr;
    QPointer<QObject> guarded(candidate);
    errno=incoming;auto connection=next(sender,signal,receiver,slot,functor,type,types,meta);int returned=errno;
    if(connection && guarded)discover(guarded.data());
    errno=returned;return connection;
}
extern "C" void af_activate(QObject *,const QMetaObject *,int,void **) asm("_ZN11QMetaObject8activateEP7QObjectPKS_iPPv");
extern "C" void af_activate(QObject *sender,const QMetaObject *meta,int signal,void **arguments){
    int incoming=errno;Activate next=resolve();bool candidate=enabled() && sender && __atomic_load_n(&messageMeta,__ATOMIC_ACQUIRE) && meta==__atomic_load_n(&messageMeta,__ATOMIC_ACQUIRE) && (signal==0 || signal==1);
    QPointer<QObject> guarded(candidate?sender:nullptr);
    QByteArray packet;
    if(candidate && signal==0 && arguments && arguments[1]){
        const auto *bytes=static_cast<const QByteArray *>(arguments[1]);
        if(bytes->size()==259){
            const auto *p=reinterpret_cast<const unsigned char *>(bytes->constData());
            if(p[0]==0x10 && p[1]==3 && p[2]==1 && p[3]==5 && as_reply(p+4))packet=*bytes;
        }
    }
    /* 原厂总是收到原始参数；私有回复也不截断 Qt 分发。 */
    errno=incoming;next(sender,meta,signal,arguments);int returned=errno;
    if(candidate && guarded){
        discover(guarded.data());
        if(!packet.isEmpty() && __atomic_load_n(&scheduledOwner,__ATOMIC_ACQUIRE)==sender)
            QTimer::singleShot(0,sender,[sender,packet](){if(auto *owned=Bus::find(sender))owned->reply(packet);});
    }
    errno=returned;
}
