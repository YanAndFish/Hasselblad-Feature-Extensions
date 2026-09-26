/* 经现有 MessageIO_UART 的 Qt 公开 slot 串行请求；不另开串口、不重配链路。 */
#include "boot_transport.h"
#include "boot_session.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qmutex.h>
#include <QtCore/qwaitcondition.h>
#include <QtCore/qthread.h>
#include <QtCore/qsavefile.h>
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qpointer.h>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <unistd.h>

namespace {
QMutex lock;
QWaitCondition changed;
QObject *source=nullptr;
QObject *discoveredSource=nullptr;
bool enabled=false,stopping=false,pending=false,received=false,failed=false,loadMode=false;
QByteArray completeReply;
uint8_t expectedReply=0;
uint32_t result=0;
unsigned requests=0;
const QMetaObject *uartMeta=nullptr;
using Connect=QMetaObject::Connection (*)(const QObject *,void **,const QObject *,void **,
    QtPrivate::QSlotObjectBase *,Qt::ConnectionType,const int *,const QMetaObject *);
Connect nextConnect=nullptr;
const QMetaObject *resolveUartMeta() {
    const QMetaObject *meta=__atomic_load_n(&uartMeta,__ATOMIC_ACQUIRE);
    if(meta)return meta;
    meta=reinterpret_cast<const QMetaObject *>(dlsym(RTLD_DEFAULT,"_ZN14MessageIO_UART16staticMetaObjectE"));
    if(meta)__atomic_store_n(&uartMeta,meta,__ATOMIC_RELEASE);
    return meta;
}
Connect resolveConnect() {
    Connect found=__atomic_load_n(&nextConnect,__ATOMIC_ACQUIRE);
    if(found)return found;
    found=reinterpret_cast<Connect>(dlsym(RTLD_NEXT,"_ZN7QObject11connectImplEPKS_PPvS1_S3_PN9QtPrivate15QSlotObjectBaseEN2Qt14ConnectionTypeEPKiPK11QMetaObject"));
    if(!found)_exit(78);
    __atomic_store_n(&nextConnect,found,__ATOMIC_RELEASE);return found;
}
bool isUart(const QObject *object) {
    const QMetaObject *meta=resolveUartMeta();
    return object && meta && object->metaObject()==meta &&
        object->metaObject()->indexOfSlot("SendMessage(QByteArray)")>=0;
}
void report(const char *stage) {
    QSaveFile f(QStringLiteral("/run/hbl-four-module/boot-transport.status"));
    if(f.open(QIODevice::WriteOnly)) {
        f.write(QByteArray("stage=")+stage+" requests="+QByteArray::number(requests)+" writes=0 pid="+QByteArray::number(getpid())+"\n");f.commit();
    }
}
uint32_t word(const char *p) {
    const auto *b=reinterpret_cast<const uint8_t *>(p);
    return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24);
}
bool readFixed(uint32_t address,uint32_t *value) {
    // 本阶段仅证明三个已绑定的只读地址。完整写入器尚未实现。
    if(!value || (address!=0x1009d4 && address!=0x6bb46c && address!=0x6bb598))return false;
    QMutexLocker guard(&lock);
    if(!enabled || stopping || failed || pending || !source || requests>=3)return false;
    char request[8]={char(0xf4),0,5,1};
    for(unsigned i=0;i<4;++i)request[4+i]=char(address>>(8*i));
    const QByteArray bytes(request,sizeof(request));
    pending=true;received=false;expectedReply=0xf5;++requests;
    if(!QMetaObject::invokeMethod(source,"SendMessage",Qt::QueuedConnection,Q_ARG(QByteArray,bytes))) {
        pending=false;failed=true;return false;
    }
    QElapsedTimer timer;timer.start();
    while(!received && !stopping) {const qint64 left=2000-timer.elapsed();if(left<=0)break;changed.wait(&lock,unsigned(left));}
    pending=false;
    if(!received || stopping || failed){failed=true;return false;}
    *value=result;return true;
}
class Probe : public QThread {
    void run() override {
        {
            QMutexLocker guard(&lock);QElapsedTimer timer;timer.start();
            while(!source && !stopping) {const qint64 left=(loadMode?30000:5000)-timer.elapsed();if(left<=0)break;changed.wait(&lock,unsigned(left));}
            if(!source || stopping){report("source-unavailable");return;}
        }
        if(loadMode) {hbl_boot_load_run();return;}
        uint32_t opcode=0,af=0,motion=0;
        if(!readFixed(0x1009d4,&opcode) || opcode!=0xe12fff1e ||
           !readFixed(0x6bb46c,&af) || (af&255) ||
           !readFixed(0x6bb598,&motion) || (motion&255)) {
            report("readonly-probe-failed");return;
        }
        report("readonly-probe-ready");
    }
};
Probe *probe=nullptr;
}
void hbl_boot_sender(QObject *sender) {
    if(!isUart(sender))return;
    QMutexLocker guard(&lock);
    if(!discoveredSource)discoveredSource=sender;
    if(discoveredSource!=sender || !enabled || stopping || source)return;
    source=sender;changed.wakeAll();
}
bool hbl_boot_reply(const QByteArray &bytes) {
    QMutexLocker guard(&lock);
    if(!enabled || stopping || !pending || bytes.size()<4)return false;
    const auto *b=reinterpret_cast<const uint8_t *>(bytes.constData());
    if(b[0]!=expectedReply || b[1] || b[2]!=1 || b[3]!=5)return false;
    if(received){failed=true;changed.wakeAll();return true;}
    if(loadMode) {completeReply=bytes;received=true;changed.wakeAll();return true;}
    if(bytes.size()!=9)return false;
    received=true;failed=b[8]!=0;result=word(bytes.constData()+4);changed.wakeAll();return true;
}
bool hbl_boot_start() {
    const char *mode=std::getenv("HBL_BOOT_READONLY_PROBE");
    const char *boot=std::getenv("HBL_BOOT_LOAD");
    const bool probeRequested=mode && !std::strcmp(mode,"1");
    const bool loadRequested=boot && !std::strcmp(boot,"1");
    if(!probeRequested && !loadRequested)return true;
    if(probeRequested && loadRequested)return false;
    QMutexLocker guard(&lock);
    if(probe || enabled)return false;
    if(!resolveUartMeta() || !QCoreApplication::instance())return false;
    loadMode=loadRequested;enabled=true;
    if(discoveredSource && isUart(discoveredSource))source=discoveredSource;
    probe=new Probe;report(source?"source-bound":"waiting-source");probe->start();return true;
}
bool hbl_boot_exchange(const QByteArray &request,QByteArray *reply) {
    QMutexLocker guard(&lock);
    if(!reply || !loadMode || !enabled || stopping || failed || pending || !source || request.size()<4 || requests>=32000)return false;
    const unsigned char opcode=static_cast<unsigned char>(request[0]);
    if(request[1]!=0 || request[2]!=5 || request[3]!=1 ||
       !((opcode==0x0d && request.size()==4) || (opcode==0xf4 && (request.size()==8 || hbl_boot_is_batch_request(request))) || (opcode==0xf2 && request.size()==12)))return false;
    pending=true;received=false;completeReply.clear();expectedReply=opcode+1;++requests;
    if(!QMetaObject::invokeMethod(source,"SendMessage",Qt::QueuedConnection,Q_ARG(QByteArray,request))) {
        pending=false;failed=true;return false;
    }
    QElapsedTimer timer;timer.start();
    while(!received && !stopping) {const qint64 left=2000-timer.elapsed();if(left<=0)break;changed.wait(&lock,unsigned(left));}
    pending=false;
    if(!received || stopping || failed){failed=true;return false;}
    *reply=completeReply;return true;
}
bool hbl_boot_pause(unsigned ms) {
    QMutexLocker guard(&lock);
    if(stopping || failed || ms>1000)return false;
    QElapsedTimer timer;timer.start();
    while(!stopping && !failed) {qint64 left=qint64(ms)-timer.elapsed();if(left<=0)return true;changed.wait(&lock,unsigned(left));}
    return false;
}
void hbl_boot_stop() {
    {QMutexLocker guard(&lock);stopping=true;changed.wakeAll();}
    if(probe){probe->wait();delete probe;probe=nullptr;}
    QMutexLocker guard(&lock);enabled=false;source=nullptr;discoveredSource=nullptr;
}

extern "C" int hbl_boot_source_test_status(QObject *expected) {
    QMutexLocker guard(&lock);
    return !enabled && !source && expected && discoveredSource==expected;
}

QMetaObject::Connection hbl_boot_connect(const QObject *,void **,const QObject *,void **,
    QtPrivate::QSlotObjectBase *,Qt::ConnectionType,const int *,const QMetaObject *)
    asm("_ZN7QObject11connectImplEPKS_PPvS1_S3_PN9QtPrivate15QSlotObjectBaseEN2Qt14ConnectionTypeEPKiPK11QMetaObject");
QMetaObject::Connection hbl_boot_connect(const QObject *sender,void **signal,const QObject *receiver,void **slot,
    QtPrivate::QSlotObjectBase *functor,Qt::ConnectionType type,const int *types,const QMetaObject *meta) {
    const int incoming=errno;Connect next=resolveConnect();
    QObject *candidate=isUart(receiver)?const_cast<QObject *>(receiver):
        (isUart(sender)?const_cast<QObject *>(sender):nullptr);
    QPointer<QObject> guarded(candidate);
    errno=incoming;QMetaObject::Connection connection=next(sender,signal,receiver,slot,functor,type,types,meta);const int returned=errno;
    if(connection && guarded)hbl_boot_sender(guarded.data());
    errno=returned;return connection;
}

QMetaObject::Connection hbl_boot_string_connect(const QObject *,const char *,const QObject *,const char *,Qt::ConnectionType)
 asm("_ZN7QObject7connectEPKS_PKcS1_S3_N2Qt14ConnectionTypeE");
QMetaObject::Connection hbl_boot_string_connect(const QObject *sender,const char *signal,const QObject *receiver,const char *slot,Qt::ConnectionType type) {
 using LegacyConnect=QMetaObject::Connection (*)(const QObject *,const char *,const QObject *,const char *,Qt::ConnectionType);
 const int incoming=errno;
 auto next=reinterpret_cast<LegacyConnect>(dlsym(RTLD_NEXT,"_ZN7QObject7connectEPKS_PKcS1_S3_N2Qt14ConnectionTypeE"));
 if(!next)return QMetaObject::Connection();
 QObject *candidate=isUart(receiver)?const_cast<QObject *>(receiver):(isUart(sender)?const_cast<QObject *>(sender):nullptr);
 QPointer<QObject> guarded(candidate);
 errno=incoming;auto connection=next(sender,signal,receiver,slot,type);const int returned=errno;
 if(connection && guarded)hbl_boot_sender(guarded.data());
 errno=returned;return connection;
}
