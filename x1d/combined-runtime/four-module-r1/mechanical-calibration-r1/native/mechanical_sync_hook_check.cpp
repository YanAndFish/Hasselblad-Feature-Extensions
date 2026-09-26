/* 独立内存检查程序：不使用 DBus、串口、相机对象或网络。 */
#include <QtCore/qcoreapplication.h>
#include <QtCore/qmetatype.h>
#include <dlfcn.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <signal.h>
#include <unistd.h>
#include "rf_receiver.h"
#include "mechanical_sync_wire.h"

/* 使用与实际信号相同的类名、签名和 Qt 5.5 元对象布局，全部对象均为自有测试对象。 */
class MessageIO_Interface : public QObject {
public:
    static const QMetaObject staticMetaObject;
    const QMetaObject *metaObject() const override { return &staticMetaObject; }
    void *qt_metacast(const char *name) override {
        if (!name) return nullptr;
        if (!std::strcmp(name, "MessageIO_Interface")) return static_cast<void *>(this);
        return QObject::qt_metacast(name);
    }
    int qt_metacall(QMetaObject::Call call, int id, void **arguments) override {
        id = QObject::qt_metacall(call, id, arguments);
        if (id < 0) return id;
        if (call == QMetaObject::InvokeMetaMethod) {
            if (id < 2) invoke(this, call, id, arguments);
            id -= 2;
        } else if (call == QMetaObject::RegisterMethodArgumentMetaType) {
            if (id < 2) *reinterpret_cast<int *>(arguments[0]) = -1;
            id -= 2;
        }
        return id;
    }
    void receive(const QByteArray &bytes) {
        void *arguments[] = {nullptr, const_cast<QByteArray *>(&bytes)};
        QMetaObject::activate(this, &staticMetaObject, 0, arguments);
    }
    void status(bool active) {
        void *arguments[] = {nullptr, &active};
        QMetaObject::activate(this, &staticMetaObject, 1, arguments);
    }
private:
    static void invoke(QObject *object, QMetaObject::Call call, int id, void **args) {
        if (call != QMetaObject::InvokeMetaMethod) return;
        auto *sender = static_cast<MessageIO_Interface *>(object);
        if (id == 0) sender->receive(*static_cast<QByteArray *>(args[1]));
        if (id == 1) sender->status(*static_cast<bool *>(args[1]));
    }
};

struct ReplyCheckStrings { QByteArrayData data[4]; char text[59]; };
#define REPLY_STRING(index, offset, length) Q_STATIC_BYTE_ARRAY_DATA_HEADER_INITIALIZER_WITH_OFFSET(length, offsetof(ReplyCheckStrings, text) + offset - index * sizeof(QByteArrayData))
static const ReplyCheckStrings replyCheckStrings = {
    {REPLY_STRING(0, 0, 19), REPLY_STRING(1, 20, 14),
     REPLY_STRING(2, 35, 0), REPLY_STRING(3, 36, 22)},
    "MessageIO_Interface\0ReceiveMessage\0\0InterfaceStatusChanged"
};
#undef REPLY_STRING
static const uint replyCheckMetadata[] = {
    7, 0, 0, 0, 2, 14, 0, 0, 0, 0, 0, 0, 0, 2,
    1, 1, 24, 2, 0x06,
    3, 1, 27, 2, 0x06,
    QMetaType::Void, QMetaType::QByteArray, 2,
    QMetaType::Void, QMetaType::Bool, 2,
    0
};
const QMetaObject MessageIO_Interface::staticMetaObject = {
    {&QObject::staticMetaObject, replyCheckStrings.data, replyCheckMetadata,
     &MessageIO_Interface::invoke, nullptr, nullptr}
};

int main(int argc, char **argv) {
    if (argc != 1) return 10;
    /* 仅约束这个独立进程的检查，不设置相机或 FARM 计时器。 */
    struct sigaction timeoutAction = {};
    timeoutAction.sa_handler = SIG_DFL;
    sigemptyset(&timeoutAction.sa_mask);
    sigset_t timeoutMask;
    sigemptyset(&timeoutMask);
    sigaddset(&timeoutMask, SIGALRM);
    if (sigaction(SIGALRM, &timeoutAction, nullptr) ||
        sigprocmask(SIG_UNBLOCK, &timeoutMask, nullptr)) return 17;
    alarm(5);
    QCoreApplication application(argc, argv);
    using Status = int (*)(uint32_t *);
    auto inspect = reinterpret_cast<Status>(dlsym(RTLD_DEFAULT, "hbl_mechanical_sync_test_status"));
    uint32_t before[3], after[3];
    if (!inspect || !inspect(before)) {
        std::puts("sync-hook-selftest-not-enabled");
        return 11;
    }
    MessageIO_Interface source;
    RfReceiver receiveCounter, statusCounter;
    unsigned received = 0, statuses = 0, submitted = 0;
    receiveCounter.received = [&] { ++received; };
    statusCounter.received = [&] { ++statuses; };
    if (!QObject::connect(&source, "2ReceiveMessage(QByteArray)", &receiveCounter,
                          "1receive()", Qt::DirectConnection) ||
        !QObject::connect(&source, "2InterfaceStatusChanged(bool)", &statusCounter,
                          "1receive()", Qt::DirectConnection)) return 12;
    auto submit = [&](const QByteArray &bytes, bool own) {
        QByteArray unchanged(bytes);
        const unsigned oldReceived=received;
        source.receive(bytes);
        if (!own) ++submitted;
        return bytes==unchanged && received==oldReceived+(own ? 0u : 1u);
    };
    uint8_t raw[261]={9,0,1,5};
    HblMechanicalSync sample={HBL_MECH_MAGIC,1,7,0x0f07,0x3001,0x3c04,100,7,1,0,3};
    const uint32_t *words=reinterpret_cast<const uint32_t *>(&sample);
    for (unsigned i=0;i<11;++i) hbl_mech_put32(raw+4+4*i,words[i]);
    for (int length=0;length<=261;++length) {
        if (length==260) continue;
        if (!submit(QByteArray(reinterpret_cast<const char *>(raw),length),false)) return 13;
    }
    const unsigned guarded[]={0,1,2,3,4,5,6,7,8,48,259};
    for (unsigned index:guarded) {
        QByteArray changed(reinterpret_cast<const char *>(raw),260);
        changed[int(index)]=char(uint8_t(changed.at(int(index)))^1);
        if (!submit(changed,false)) return 14;
    }
    for (uint32_t flags:{uint32_t(7),uint32_t(5),uint32_t(4),uint32_t(0x0f07),uint32_t(0x8007)}) {
        hbl_mech_put32(raw+16,flags);
        if (!submit(QByteArray(reinterpret_cast<const char *>(raw),260),true)) return 15;
    }
    source.status(true);
    if (!inspect(after) || after[0]-before[0]!=5 || after[1]!=7 ||
        after[2]-before[2]!=submitted || received!=submitted || statuses!=1) return 16;
    std::printf("sync-hook-selftest: own=5 forwarded=%u status=1 hardware=0\n",received);
    return 0;
}
