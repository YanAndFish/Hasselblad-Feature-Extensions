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
#include "farm_reply_wire.h"

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
    auto inspect = reinterpret_cast<Status>(dlsym(RTLD_DEFAULT, "hbl_farm_reply_test_status"));
    uint32_t before[3], after[3];
    if (!inspect || !inspect(before)) {
        std::puts("reply-hook-selftest-not-enabled");
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
    auto submit = [&](const QByteArray &bytes) {
        QByteArray unchanged(bytes);
        source.receive(bytes);
        ++submitted;
        return bytes == unchanged && received == submitted;
    };
    const uint8_t raw[10] = {0xf5, 0, 1, 5, 0x78, 0x56, 0x34, 0x12, 0, 0};
    for (int length = 0; length <= 10; ++length) {
        if (length == 9) continue;
        if (!submit(QByteArray(reinterpret_cast<const char *>(raw), length))) return 13;
    }
    const unsigned guarded[] = {0, 1, 2, 3, 8};
    for (unsigned index : guarded) {
        QByteArray changed(reinterpret_cast<const char *>(raw), 9);
        changed[static_cast<int>(index)] = char(uint8_t(changed.at(index)) ^ 1);
        if (!submit(changed)) return 14;
    }
    for (uint32_t value : {uint32_t(0), uint32_t(0x12345678), uint32_t(0xffffffff)}) {
        uint8_t bytes[9];
        std::memcpy(bytes, raw, sizeof(bytes));
        hbl_reply_put32(bytes + 4, value);
        if (!submit(QByteArray(reinterpret_cast<const char *>(bytes), sizeof(bytes)))) return 15;
    }
    source.status(true);
    if (!inspect(after) || after[0] - before[0] != 3 || after[1] != 0xffffffff ||
        after[2] - before[2] != submitted || received != submitted || statuses != 1) return 16;
    std::printf("reply-hook-selftest: valid=3 rejected=15 forwarded=%u status=1 hardware=0\n", received);
    return 0;
}
