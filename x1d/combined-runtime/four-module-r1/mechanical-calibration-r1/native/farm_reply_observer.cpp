/* 仅供固定版本研究；尚未加入安装包。没有请求、串口、曝光或无线发射入口。 */
#include <QtCore/qbytearray.h>
#include <QtCore/qobject.h>
#include <dlfcn.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include "farm_reply_wire.h"

static_assert(QT_VERSION == 0x050501, "Requires the audited Qt 5.5.1 headers");
static_assert(sizeof(void *) == 4 && sizeof(QByteArray) == 4, "Requires the audited ARM32 ABI");

using Activate = void (*)(QObject *, const QMetaObject *, int, void **);
static Activate originalActivate;
static const QMetaObject *messageMeta;
static bool selfTest;
static int outputFd = -1;
static unsigned outputEnabled;
static uint32_t acceptedCount, lastValue, forwardedCount, sequence;

static Activate resolveActivate() {
    Activate found = __atomic_load_n(&originalActivate, __ATOMIC_ACQUIRE);
    if (found) return found;
    found = reinterpret_cast<Activate>(
        dlsym(RTLD_NEXT, "_ZN11QMetaObject8activateEP7QObjectPKS_iPPv"));
    if (!found) _exit(78);
    __atomic_store_n(&originalActivate, found, __ATOMIC_RELEASE);
    return found;
}

static bool flag(const char *name) {
    const char *value = std::getenv(name);
    return value && std::strcmp(value, "1") == 0;
}

__attribute__((constructor)) static void initializeObserver() {
    /* 原函数无法解析时拒绝进程启动，不能静默吞掉全部 Qt 信号。
       因此部署前必须先在独立检查程序中通过同机 Qt/loader 验证。 */
    resolveActivate();
    messageMeta = reinterpret_cast<const QMetaObject *>(
        dlsym(RTLD_DEFAULT, "_ZN19MessageIO_Interface16staticMetaObjectE"));
    selfTest = flag("HBL_FARM_REPLY_SELFTEST");
    if (selfTest || !messageMeta || !flag("HBL_FARM_REPLY_OBSERVE")) return;

    const char *directory = "/tmp/hbl-wireless-flash";
    const char *path = "/tmp/hbl-wireless-flash/farm-reply.sock";
    struct stat ds, ss;
    if (lstat(directory, &ds) || !S_ISDIR(ds.st_mode) || ds.st_uid != geteuid() ||
        (ds.st_mode & 0777) != 0700 || lstat(path, &ss) || !S_ISSOCK(ss.st_mode) ||
        ss.st_uid != geteuid() || (ss.st_mode & 0777) != 0600) return;
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) return;
    sockaddr_un peer = {};
    peer.sun_family = AF_UNIX;
    std::memcpy(peer.sun_path, path, std::strlen(path) + 1);
    if (connect(fd, reinterpret_cast<sockaddr *>(&peer), sizeof(peer))) {
        close(fd);
        return;
    }
    outputFd = fd;
    __atomic_store_n(&outputEnabled, 1, __ATOMIC_RELEASE);
}

__attribute__((destructor)) static void closeObserver() {
    __atomic_store_n(&outputEnabled, 0, __ATOMIC_RELEASE);
    if (outputFd >= 0) close(outputFd);
}

extern "C" void hbl_observe_activate(QObject *, const QMetaObject *, int, void **)
    asm("_ZN11QMetaObject8activateEP7QObjectPKS_iPPv");

extern "C" void hbl_observe_activate(QObject *sender, const QMetaObject *meta,
                                      int signal, void **arguments) {
    const int incomingErrno = errno;
    /* Qt 的其他初始化函数可能早于本库构造函数发出信号。 */
    Activate forward = resolveActivate();
    const bool candidate = messageMeta && meta == messageMeta && signal == 0;
    uint32_t value = 0;
    bool accepted = false;
    if (candidate && (selfTest || __atomic_load_n(&outputEnabled, __ATOMIC_ACQUIRE)) &&
        arguments && arguments[1]) {
        const auto *bytes = static_cast<const QByteArray *>(arguments[1]);
        accepted = hbl_parse_farm_reply(
            reinterpret_cast<const uint8_t *>(bytes->constData()),
            static_cast<size_t>(bytes->size()), &value) != 0;
    }

    /* 每次都先完成原始分发，再处理自有记录；不改变 sender/meta/参数。 */
    errno = incomingErrno;
    forward(sender, meta, signal, arguments);
    struct RestoreErrno {
        int value;
        ~RestoreErrno() { errno = value; }
    } restoreErrno{errno};
    if (selfTest && candidate) __atomic_add_fetch(&forwardedCount, 1, __ATOMIC_RELAXED);
    if (!accepted) return;
    if (selfTest) {
        __atomic_store_n(&lastValue, value, __ATOMIC_RELAXED);
        __atomic_add_fetch(&acceptedCount, 1, __ATOMIC_RELAXED);
        return;
    }
    if (!__atomic_load_n(&outputEnabled, __ATOMIC_ACQUIRE)) return;
    timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) || now.tv_sec < 0 ||
        now.tv_nsec < 0 || now.tv_nsec >= 1000000000) return;
    uint32_t seq = __atomic_add_fetch(&sequence, 1, __ATOMIC_RELAXED);
    if (!seq) seq = __atomic_add_fetch(&sequence, 1, __ATOMIC_RELAXED);
    uint8_t packet[24];
    hbl_pack_farm_reply(packet, seq, value,
                       uint64_t(now.tv_sec) * 1000000000u + uint64_t(now.tv_nsec));
    if (send(outputFd, packet, sizeof(packet), MSG_DONTWAIT | MSG_NOSIGNAL) !=
        static_cast<ssize_t>(sizeof(packet))) {
        /* 队列满或接收者退出后停用输出；没有重试、重连或补发。 */
        __atomic_store_n(&outputEnabled, 0, __ATOMIC_RELEASE);
    }
}

extern "C" int hbl_farm_reply_test_status(uint32_t out[3]) {
    if (!selfTest || !originalActivate || !messageMeta || !out) return 0;
    out[0] = __atomic_load_n(&acceptedCount, __ATOMIC_RELAXED);
    out[1] = __atomic_load_n(&lastValue, __ATOMIC_RELAXED);
    out[2] = __atomic_load_n(&forwardedCount, __ATOMIC_RELAXED);
    return 1;
}
