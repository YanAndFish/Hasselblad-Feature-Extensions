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
#include <cstddef>
extern "C" {
#include "settings_wire.h"
}
#include "settings_socket.h"
static_assert(QT_VERSION==0x050501 && sizeof(void *)==4 && sizeof(QByteArray)==4,"Fixed ARM Qt ABI");
namespace {
using Activate=void (*)(QObject *,const QMetaObject *,int,void **);
Activate nextActivate=nullptr;const QMetaObject *messageMeta=nullptr;
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
        fd=as_bind(AS_BACKEND);if(fd<0)return;
        auto notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int){receive();});clock.start();
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
}
__attribute__((constructor)) static void setup(){
    resolve();messageMeta=reinterpret_cast<const QMetaObject *>(dlsym(RTLD_DEFAULT,"_ZN19MessageIO_Interface16staticMetaObjectE"));
}
extern "C" void af_activate(QObject *,const QMetaObject *,int,void **) asm("_ZN11QMetaObject8activateEP7QObjectPKS_iPPv");
extern "C" void af_activate(QObject *sender,const QMetaObject *meta,int signal,void **arguments){
    int incoming=errno;Activate next=resolve();bool candidate=enabled() && sender && messageMeta && meta==messageMeta && (signal==0 || signal==1);
    QPointer<QObject> guarded(candidate?sender:nullptr);
    QByteArray packet;
    if(candidate && signal==0 && arguments && arguments[1]){
        const auto *bytes=static_cast<const QByteArray *>(arguments[1]);
        if(bytes->size()==259){
            const auto *p=reinterpret_cast<const unsigned char *>(bytes->constData());
            if(p[0]==0x10 && p[1]==3 && p[2]==1 && p[3]==5 && as_reply(p+4))packet=*bytes;
        }
    }
    /* 原厂和正式闪光 observer 总是收到原始参数；私有回复也不截断 Qt 分发。 */
    errno=incoming;next(sender,meta,signal,arguments);int returned=errno;
    if(candidate && guarded){
        QObject *expected=nullptr;
        if(__atomic_compare_exchange_n(&scheduledOwner,&expected,sender,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
            /* owner 在 singleShot 执行前销毁时，Qt 会取消回调，仍必须释放选择。 */
            QObject::connect(sender,&QObject::destroyed,[](QObject *object){
                QObject *expectedOwner=object;
                __atomic_compare_exchange_n(&scheduledOwner,&expectedOwner,nullptr,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
            });
            QTimer::singleShot(0,sender,[sender](){
                if(Bus::find(sender) || sender->metaObject()->indexOfMethod("SendMessage(QByteArray)")<0){
                    QObject *expectedOwner=sender;
                    __atomic_compare_exchange_n(&scheduledOwner,&expectedOwner,nullptr,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);return;
                }
                new Bus(sender);
            });
        }
        if(!packet.isEmpty() && __atomic_load_n(&scheduledOwner,__ATOMIC_ACQUIRE)==sender)
            QTimer::singleShot(0,sender,[sender,packet](){if(auto *owned=Bus::find(sender))owned->reply(packet);});
    }
    errno=returned;
}
