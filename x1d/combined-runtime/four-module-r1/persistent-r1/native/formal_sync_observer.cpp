/* X1D 1.25.0：只消费完整 GMS1/GFS3 自有消息，在同一进程交给无线 worker。 */
#include <QtCore/qbytearray.h>
#include <QtCore/qobject.h>
#include <dlfcn.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
#include "mechanical_sync_wire.h"
#include "farm_sync_wire.h"
#include "boot_transport.h"
static_assert(QT_VERSION==0x050501,"Requires audited Qt 5.5.1");
static_assert(sizeof(void *)==4 && sizeof(QByteArray)==4,"Requires audited ARM32 ABI");
using Activate=void (*)(QObject *,const QMetaObject *,int,void **);
static Activate originalActivate;
static const QMetaObject *messageMeta;
static bool selfTest,observeEnabled,workerStarted;
static uint32_t outputEnabled,acceptedCount,forwardedCount,lastShot,epoch;
extern "C" bool hbl_formal_begin();
extern "C" void hbl_formal_deliver_mech(uint32_t,const HblMechanicalSync *,uint64_t);
extern "C" void hbl_formal_deliver_es(uint32_t,const HblFarmSync *,uint64_t);
extern "C" void hbl_formal_end();
static Activate resolveActivate() {
    Activate found=__atomic_load_n(&originalActivate,__ATOMIC_ACQUIRE);
    if (found) return found;
    found=reinterpret_cast<Activate>(dlsym(RTLD_NEXT,"_ZN11QMetaObject8activateEP7QObjectPKS_iPPv"));
    if (!found) _exit(78);
    __atomic_store_n(&originalActivate,found,__ATOMIC_RELEASE); return found;
}
static bool flag(const char *name) {
    const char *v=std::getenv(name); return v && std::strcmp(v,"1")==0;
}
static void health(const char *stage) {
    if (selfTest) return;
    const int saved=errno;
    const int fd=open("/tmp/hbl-wireless-flash/formal-observer.status",O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd>=0) {
        char text[96];
        const int n=std::snprintf(text,sizeof(text),"stage=%s meta=%u observe=%u\n",stage,unsigned(messageMeta!=nullptr),unsigned(observeEnabled));
        if (n>0 && n<int(sizeof(text))) (void)write(fd,text,size_t(n));
        close(fd);
    }
    errno=saved;
}
__attribute__((constructor)) static void initializeFormalSync() {
    resolveActivate();
    messageMeta=reinterpret_cast<const QMetaObject *>(dlsym(RTLD_DEFAULT,"_ZN19MessageIO_Interface16staticMetaObjectE"));
    selfTest=flag("HBL_FORMAL_SYNC_SELFTEST");
    observeEnabled=flag("HBL_FORMAL_SYNC_OBSERVE");
}
extern "C" void hbl_formal_activate(QObject *,const QMetaObject *,int,void **)
    asm("_ZN11QMetaObject8activateEP7QObjectPKS_iPPv");
extern "C" void hbl_formal_activate(QObject *sender,const QMetaObject *meta,int signal,void **arguments) {
    const int incomingErrno=errno;
    Activate forward=resolveActivate();
    const bool candidate=messageMeta && meta==messageMeta && signal==0;
    if(candidate && !selfTest && arguments && arguments[1]) {
        hbl_boot_sender(sender);
        if(hbl_boot_reply(*static_cast<const QByteArray *>(arguments[1]))) {errno=incomingErrno;return;}
    }
    HblMechanicalSync mech={}; HblFarmSync es={};
    bool ownMech=false,ownEs=false;
    if (candidate && (selfTest || observeEnabled) && arguments && arguments[1]) {
        const auto *bytes=static_cast<const QByteArray *>(arguments[1]);
        const auto *data=reinterpret_cast<const uint8_t *>(bytes->constData());
        const size_t length=size_t(bytes->size());
        ownMech=hbl_parse_mech_message(data,length,&mech)!=0;
        if (!ownMech) ownEs=hbl_parse_sync_message(data,length,&es)!=0;
    }
    if (!ownMech && !ownEs) {
        errno=incomingErrno; forward(sender,meta,signal,arguments);
        if (selfTest && candidate) __atomic_add_fetch(&forwardedCount,1,__ATOMIC_RELAXED);
        return;
    }
    struct RestoreErrno { int value; ~RestoreErrno() { errno=value; } } restore{incomingErrno};
    if (selfTest) {
        __atomic_add_fetch(&acceptedCount,1,__ATOMIC_RELAXED);
        __atomic_store_n(&lastShot,ownMech ? mech.trial:es.shot,__ATOMIC_RELAXED); return;
    }
    if (!__atomic_load_n(&outputEnabled,__ATOMIC_ACQUIRE)) return;
    timespec now={};
    if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec<0 || now.tv_nsec<0 || now.tv_nsec>=1000000000) return;
    const uint64_t arrival=uint64_t(now.tv_sec)*1000000000u+uint64_t(now.tv_nsec);
    if (ownMech) hbl_formal_deliver_mech(epoch,&mech,arrival);
    else hbl_formal_deliver_es(epoch,&es,arrival);
}
extern "C" int hbl_formal_sync_test_status(uint32_t out[3]) {
    if (!selfTest || !originalActivate || !messageMeta || !out) return 0;
    out[0]=__atomic_load_n(&acceptedCount,__ATOMIC_RELAXED);
    out[1]=__atomic_load_n(&lastShot,__ATOMIC_RELAXED);
    out[2]=__atomic_load_n(&forwardedCount,__ATOMIC_RELAXED); return 1;
}
extern "C" int hbl_formal_exec() asm("_ZN16QCoreApplication4execEv");
extern "C" int hbl_formal_exec() {
    using Exec=int (*)();
    auto original=reinterpret_cast<Exec>(dlsym(RTLD_NEXT,"_ZN16QCoreApplication4execEv"));
    if (!original) return 78;
    if (observeEnabled && !selfTest && !workerStarted) {
        timespec now={};
        if (!messageMeta || clock_gettime(CLOCK_MONOTONIC,&now) || !hbl_formal_begin() || !hbl_boot_start()) {
            health("embedded-start-failed"); return 79;
        }
        workerStarted=true;
        epoch=uint32_t(now.tv_nsec)^uint32_t(now.tv_sec)^uint32_t(getpid());
        if (!epoch) epoch=1;
        __atomic_store_n(&outputEnabled,1,__ATOMIC_RELEASE); health("ready");
    }
    const int result=original();
    hbl_boot_stop();
    if (workerStarted) {
        __atomic_store_n(&outputEnabled,0,__ATOMIC_RELEASE);
        hbl_formal_end(); workerStarted=false;
    }
    return result;
}
