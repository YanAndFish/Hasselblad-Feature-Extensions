/* 独立临时只读验证器；与已验收 observer 串联，不替换其代码和无线策略。 */
#include "boot_transport.h"
#include <QtCore/qmetaobject.h>
#include <dlfcn.h>
#include <cerrno>
#include <unistd.h>
using Activate=void (*)(QObject *,const QMetaObject *,int,void **);
extern "C" void boot_probe_activate(QObject *,const QMetaObject *,int,void **)
    asm("_ZN11QMetaObject8activateEP7QObjectPKS_iPPv");
extern "C" void boot_probe_activate(QObject *sender,const QMetaObject *meta,int signal,void **arguments) {
    const int saved=errno;
    static auto original=reinterpret_cast<Activate>(dlsym(RTLD_NEXT,"_ZN11QMetaObject8activateEP7QObjectPKS_iPPv"));
    static auto messageMeta=reinterpret_cast<const QMetaObject *>(dlsym(RTLD_DEFAULT,"_ZN19MessageIO_Interface16staticMetaObjectE"));
    if(!original)_exit(78);
    if(messageMeta && meta==messageMeta && signal==0 && arguments && arguments[1]) {
        hbl_boot_sender(sender);
        if(hbl_boot_reply(*static_cast<const QByteArray *>(arguments[1]))){errno=saved;return;}
    }
    errno=saved;original(sender,meta,signal,arguments);
}
extern "C" int boot_probe_exec() asm("_ZN16QCoreApplication4execEv");
extern "C" int boot_probe_exec() {
    using Exec=int (*)();
    static auto original=reinterpret_cast<Exec>(dlsym(RTLD_NEXT,"_ZN16QCoreApplication4execEv"));
    if(!original || !hbl_boot_start())return 78;
    const int result=original();hbl_boot_stop();return result;
}
