#ifndef HBL_FORMAL_RADIO_FAKE_PLATFORM_H
#define HBL_FORMAL_RADIO_FAKE_PLATFORM_H
/* 测试替身只在主机内存中排队；不导入真实 socket、进程或专用线程实现。 */
#include <functional>
#include <memory>
#include <string>
#include <vector>
#include <deque>
#include <map>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cstddef>
#include <cstdlib>
#include <cerrno>
#include <ctime>
#include <sstream>
#include <iostream>
#include <stdexcept>
typedef unsigned uint;
typedef std::ptrdiff_t ssize_t;
typedef unsigned socklen_t;
namespace formal_test {
static std::deque<std::function<void()>> posted;
static std::deque<std::vector<uint8_t>> sent,received;
static std::vector<unsigned> selectors;
static std::vector<std::vector<std::string>> processes;
static unsigned sockets=0,attempts=0;
static int failSelector=-1;
static bool rejectSchedule=false,threadValid=true,rejectSocket=false;
static uint64_t clockUs=1000000;
}
class QString {
public:
    std::string value;
    QString()=default;
    QString(const char *s):value(s) {}
    QString(const std::string &s):value(s) {}
    static QString number(unsigned n) { return QString(std::to_string(n)); }
    QString operator+(const QString &other) const { return QString(value+other.value); }
    void clear() { value.clear(); }
};
#define QStringLiteral(s) QString(s)
template<class T> class QList: public std::vector<T> {
public: int size() const { return int(std::vector<T>::size()); }
};
class QByteArray {
public:
    std::string value;
    QByteArray()=default;
    QByteArray(const char *s):value(s) {}
    QByteArray(const std::string &s):value(s) {}
    bool isEmpty() const { return value.empty(); }
    int size() const { return int(value.size()); }
    bool startsWith(const QByteArray &other) const { return value.compare(0,other.value.size(),other.value)==0; }
    QByteArray mid(int offset) const { return offset>=size() ? QByteArray() : QByteArray(value.substr(size_t(offset))); }
    QByteArray trimmed() const {
        const auto begin=value.find_first_not_of(" \t\r\n"),end=value.find_last_not_of(" \t\r\n");
        return begin==std::string::npos ? QByteArray() : QByteArray(value.substr(begin,end-begin+1));
    }
    QByteArray simplified() const {
        std::istringstream stream(value); std::string token,out;
        while(stream>>token) { if (!out.empty()) out+=' '; out+=token; }
        return QByteArray(out);
    }
    QList<QByteArray> split(char separator) const {
        QList<QByteArray> parts; std::istringstream stream(value); std::string token;
        while(std::getline(stream,token,separator)) parts.push_back(QByteArray(token));
        return parts;
    }
    uint toUInt(bool *ok,int base) const {
        char *end=nullptr; const unsigned long n=std::strtoul(value.c_str(),&end,base);
        *ok=!value.empty() && end && !*end && n<=UINT32_MAX; return uint(n);
    }
    bool operator!=(const char *other) const { return value!=other; }
};
class QStringList {
public:
    std::vector<std::string> values;
    QStringList &operator<<(const QString &s) { values.push_back(s.value); return *this; }
};
class QObject {
public:
    std::shared_ptr<int> alive=std::make_shared<int>(1);
    explicit QObject(QObject * =nullptr) {}
    virtual ~QObject() { alive.reset(); }
    template<class... T> static void connect(T...) {}
};
class QProcessEnvironment {
public:
    static QProcessEnvironment systemEnvironment() { return QProcessEnvironment(); }
    void remove(const QString &) {}
};
class QProcess: public QObject {
public:
    enum ExitStatus { NormalExit,CrashExit };
    enum ProcessError { FailedToStart };
    enum ProcessState { NotRunning,Running };
    enum ProcessChannelMode { SeparateChannels };
    ProcessState current=NotRunning;
    QByteArray output;
    void setProcessEnvironment(const QProcessEnvironment &) {}
    QProcessEnvironment processEnvironment() const { return QProcessEnvironment(); }
    void setProcessChannelMode(ProcessChannelMode) {}
    void start(const QString &executable,const QStringList &args) {
        if (executable.value!="/usr/bin/wl") throw std::runtime_error("unexpected executable");
        formal_test::processes.push_back(args.values); current=Running;
    }
    ProcessState state() const { return current; }
    void kill() { current=NotRunning; }
    bool waitForFinished(int) { current=NotRunning; return true; }
    QByteArray readAllStandardOutput() { const auto answer=output; output=QByteArray(); return answer; }
    QByteArray readAllStandardError() { return QByteArray(); }
    void finished(int,ExitStatus) {}
    void error(ProcessError) {}
};
class QTimer: public QObject {
public:
    bool active=false;
    void setSingleShot(bool) {}
    void start(int) { active=true; }
    void stop() { active=false; }
    void timeout() {}
    template<class F> static void singleShot(int,QObject *owner,F callback) {
        std::weak_ptr<int> weak=owner->alive;
        formal_test::posted.push_back([weak,callback]() { if (!weak.expired()) callback(); });
    }
};
class QSocketNotifier: public QObject {
public:
    enum Type { Read };
    bool enabled=true;
    QSocketNotifier(int,Type,QObject *) {}
    void setEnabled(bool on) { enabled=on; }
    void activated(int) {}
};
enum { AF_NETLINK=16,SOCK_RAW=3,SOCK_NONBLOCK=2048,SOCK_CLOEXEC=524288,NETLINK_GENERIC=16,
       MSG_DONTWAIT=64,MSG_NOSIGNAL=16384,MSG_TRUNC=32 };
struct sockaddr { unsigned short family; char bytes[14]; };
struct sockaddr_nl { unsigned short nl_family,padding; uint32_t nl_pid,nl_groups; };
struct iovec { void *iov_base; size_t iov_len; };
struct msghdr { void *msg_name; socklen_t msg_namelen; iovec *msg_iov; size_t msg_iovlen; int msg_flags; };
static inline unsigned if_nametoindex(const char *name) { return std::strcmp(name,"wlp1s0") ? 0 : 4; }
static inline int socket(int,int,int) { if (formal_test::rejectSocket) return -1; ++formal_test::sockets; return 10; }
static inline int bind(int,const sockaddr *,socklen_t) { return 0; }
static inline int getsockname(int,sockaddr *address,socklen_t *) {
    auto *p=reinterpret_cast<sockaddr_nl *>(address); p->nl_family=AF_NETLINK; p->nl_pid=99; return 0;
}
static inline int close(int) { --formal_test::sockets; return 0; }
static inline ssize_t sendto(int,const void *bytes,size_t size,int,const sockaddr *,socklen_t) {
    const auto *p=static_cast<const uint8_t *>(bytes); ++formal_test::attempts;
    if (size==76) {
        const unsigned selector=unsigned(p[68])|(unsigned(p[69])<<8)|(unsigned(p[70])<<16)|(unsigned(p[71])<<24);
        formal_test::selectors.push_back(selector);
        if (int(selector)==formal_test::failSelector) return -1;
    }
    formal_test::sent.push_back(std::vector<uint8_t>(p,p+size)); return ssize_t(size);
}
static inline ssize_t recvmsg(int,msghdr *message,int) {
    if (formal_test::received.empty()) { errno=EAGAIN; return -1; }
    auto bytes=formal_test::received.front(); formal_test::received.pop_front();
    if (bytes.size()>message->msg_iov->iov_len) { message->msg_flags=MSG_TRUNC; return ssize_t(bytes.size()); }
    std::memcpy(message->msg_iov->iov_base,bytes.data(),bytes.size());
    auto *peer=static_cast<sockaddr_nl *>(message->msg_name); peer->nl_family=AF_NETLINK; peer->nl_pid=0;
    return ssize_t(bytes.size());
}
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif
static inline int formal_fake_clock(int,timespec *at) {
    at->tv_sec=time_t(formal_test::clockUs/1000000); at->tv_nsec=long(formal_test::clockUs%1000000)*1000; return 0;
}
#define clock_gettime formal_fake_clock
class MechanicalDirectDispatch {
public:
    enum Result { Empty=0,Submitted=1,Cancelled=2,Failed=3 };
    bool pending=false;
    Result result=Empty;
    std::vector<uint8_t> bytes;
    uint64_t target=0;
    bool valid() const { return formal_test::threadValid; }
    int completionFd() const { return 12; }
    bool schedule(int,const void *packet,size_t size,const sockaddr *,socklen_t,uint64_t at) {
        if (!valid() || formal_test::rejectSchedule || pending || result!=Empty || !at) return false;
        auto *p=static_cast<const uint8_t *>(packet); bytes.assign(p,p+size); pending=true; target=at; return true;
    }
    Result take() { const auto answer=result; result=Empty; return answer; }
    Result cancel() {
        if (pending) { pending=false; return Cancelled; }
        return take();
    }
    void submit() {
        if (!pending) throw std::runtime_error("no dispatch pending");
        pending=false;
        result=sendto(10,bytes.data(),bytes.size(),0,nullptr,0)==ssize_t(bytes.size()) ? Submitted : Failed;
    }
};
#endif
