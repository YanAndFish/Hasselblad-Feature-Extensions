/* 固定 X1D 1.25 的自有 GMS1 消息接收候选，尚未安装。
 * 原厂消息均原样分发；只消费本候选新增的完整 GMS1 容器。
 */
#include <QtCore/qbytearray.h>
#include <QtCore/qobject.h>
#include <dlfcn.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include "mechanical_sync_wire.h"

static_assert(QT_VERSION==0x050501,"Requires audited Qt 5.5.1");
static_assert(sizeof(void *)==4 && sizeof(QByteArray)==4,"Requires audited ARM32 ABI");
using Activate=void (*)(QObject *,const QMetaObject *,int,void **);
static Activate originalActivate;
static const QMetaObject *messageMeta;
static bool selfTest,observeEnabled;
static int outputFd=-1;
static unsigned outputEnabled;
static uint32_t acceptedCount,forwardedCount,lastShot,epoch;

/* 固定 ARM32 glibc 2.22 的 __lxstat64 直接使用 104 字节 kernel stat64。
 * 现代工具链 lstat 的版本参数会被旧 __xstat_conv 拒绝（实机 EINVAL）。
 * 不改权限策略；仅用已核对的旧 ABI 读取 mode/uid。
 */
extern "C" int __lxstat64(int,const char *,void *);
static int legacyStat(const char *path,uint32_t &mode,uint32_t &uid) {
    alignas(8) uint8_t bytes[104]={};
    if (__lxstat64(3,path,bytes)) return -1;
    std::memcpy(&mode,bytes+16,4);
    std::memcpy(&uid,bytes+24,4);
    return 0;
}

static void health(const char *stage,int error=0,unsigned detail=0) {
    if (selfTest) return;
    const int saved=errno;
    const int fd=open("/tmp/hbl-wireless-flash/mechanical-observer.status",O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd>=0) {
        char text[160];
        const int n=std::snprintf(text,sizeof(text),"stage=%s error=%d detail=%u meta=%u observe=%u output=%u accepted=%u shot=%u\n",
            stage,error,detail,unsigned(messageMeta!=nullptr),unsigned(observeEnabled),outputEnabled,acceptedCount,lastShot);
        if (n>0 && n<int(sizeof(text))) (void)write(fd,text,size_t(n));
        close(fd);
    }
    errno=saved;
}

static Activate resolveActivate() {
    Activate found=__atomic_load_n(&originalActivate,__ATOMIC_ACQUIRE);
    if (found) return found;
    found=reinterpret_cast<Activate>(dlsym(RTLD_NEXT,"_ZN11QMetaObject8activateEP7QObjectPKS_iPPv"));
    if (!found) _exit(78);
    __atomic_store_n(&originalActivate,found,__ATOMIC_RELEASE);
    return found;
}
static bool flag(const char *name) {
    const char *v=std::getenv(name);
    return v && std::strcmp(v,"1")==0;
}
__attribute__((constructor)) static void initializeSync() {
    resolveActivate();
    messageMeta=reinterpret_cast<const QMetaObject *>(dlsym(RTLD_DEFAULT,"_ZN19MessageIO_Interface16staticMetaObjectE"));
    selfTest=flag("HBL_MECHANICAL_SYNC_SELFTEST");
    observeEnabled=flag("HBL_MECHANICAL_SYNC_OBSERVE");
    if (selfTest) return;
    if (!messageMeta || !observeEnabled) { health("disabled"); return; }
    uint32_t directoryMode,directoryUid,socketMode,socketUid;
    if (legacyStat("/tmp/hbl-wireless-flash",directoryMode,directoryUid)) { health("directory-stat",errno); return; }
    if (!S_ISDIR(directoryMode) || directoryUid!=geteuid() || (directoryMode&0777)!=0700) {
        health("directory-policy",0,directoryMode); return;
    }
    if (legacyStat(HBL_MECH_SOCKET,socketMode,socketUid)) { health("socket-stat",errno); return; }
    if (!S_ISSOCK(socketMode) || socketUid!=geteuid() || (socketMode&0777)!=0600) {
        health("socket-policy",0,socketMode); return;
    }
    timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec<0 || now.tv_nsec<0 || now.tv_nsec>=1000000000) { health("clock",errno); return; }
    epoch=uint32_t(now.tv_nsec)^uint32_t(now.tv_sec)^uint32_t(getpid());
    if (!epoch) epoch=1;
    int fd=socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
    if (fd<0) { health("socket-create",errno); return; }
    sockaddr_un peer={}; peer.sun_family=AF_UNIX;
    std::memcpy(peer.sun_path,HBL_MECH_SOCKET,sizeof(HBL_MECH_SOCKET));
    if (connect(fd,reinterpret_cast<sockaddr *>(&peer),sizeof(peer))) { const int e=errno; close(fd); health("socket-connect",e); return; }
    outputFd=fd;
    __atomic_store_n(&outputEnabled,1,__ATOMIC_RELEASE);
    health("ready");
}
__attribute__((destructor)) static void closeSync() {
    __atomic_store_n(&outputEnabled,0,__ATOMIC_RELEASE);
    if (outputFd>=0) close(outputFd);
}
extern "C" void hbl_sync_activate(QObject *,const QMetaObject *,int,void **)
    asm("_ZN11QMetaObject8activateEP7QObjectPKS_iPPv");
extern "C" void hbl_sync_activate(QObject *sender,const QMetaObject *meta,int signal,void **arguments) {
    const int incomingErrno=errno;
    Activate forward=resolveActivate();
    const bool candidate=messageMeta && meta==messageMeta && signal==0;
    HblMechanicalSync sample={};
    bool own=false;
    if (candidate && (selfTest || observeEnabled) && arguments && arguments[1]) {
        const auto *bytes=static_cast<const QByteArray *>(arguments[1]);
        own=hbl_parse_mech_message(reinterpret_cast<const uint8_t *>(bytes->constData()),
                                   size_t(bytes->size()),&sample)!=0;
    }
    if (!own) {
        if (candidate && !selfTest && arguments && arguments[1]) {
            const auto *bytes=static_cast<const QByteArray *>(arguments[1]);
            if (bytes->size()>=8 && hbl_mech_u32(reinterpret_cast<const uint8_t *>(bytes->constData())+4)==HBL_MECH_MAGIC)
                health("own-message-rejected",0,unsigned(bytes->size()));
        }
        errno=incomingErrno;
        forward(sender,meta,signal,arguments);
        if (selfTest && candidate) __atomic_add_fetch(&forwardedCount,1,__ATOMIC_RELAXED);
        return;
    }
    struct RestoreErrno { int value; ~RestoreErrno() { errno=value; } } restore{incomingErrno};
    if (selfTest) {
        __atomic_add_fetch(&acceptedCount,1,__ATOMIC_RELAXED);
        __atomic_store_n(&lastShot,sample.trial,__ATOMIC_RELAXED);
        return;
    }
    if (!__atomic_load_n(&outputEnabled,__ATOMIC_ACQUIRE)) return;
    timespec now;
    if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec<0 || now.tv_nsec<0 || now.tv_nsec>=1000000000) return;
    uint8_t packet[64];
    hbl_pack_mech_ipc(packet,epoch,&sample,uint64_t(now.tv_sec)*1000000000u+uint64_t(now.tv_nsec));
    if (send(outputFd,packet,sizeof(packet),MSG_DONTWAIT|MSG_NOSIGNAL)!=ssize_t(sizeof(packet))) {
        __atomic_store_n(&outputEnabled,0,__ATOMIC_RELEASE);
        health("send-failed",errno);
    }
}
extern "C" int hbl_mechanical_sync_test_status(uint32_t out[3]) {
    if (!selfTest || !originalActivate || !messageMeta || !out) return 0;
    out[0]=__atomic_load_n(&acceptedCount,__ATOMIC_RELAXED);
    out[1]=__atomic_load_n(&lastShot,__ATOMIC_RELAXED);
    out[2]=__atomic_load_n(&forwardedCount,__ATOMIC_RELAXED);
    return 1;
}
