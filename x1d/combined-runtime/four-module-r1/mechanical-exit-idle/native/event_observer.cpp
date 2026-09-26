#include "rf_receiver.h"
#include "rf_int_receiver.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qtimer.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusreply.h>
#include <QtDBus/qdbusservicewatcher.h>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <fcntl.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

// 同版 ARM glibc 2.22 的 __xstat_conv 只接受此用户态结构版本。
// 当前 Zig 打包的 lstat/fstat thunk 使用通用版本 0，会被原厂库拒绝。
extern "C" int __lxstat(int,const char *,struct stat *);
extern "C" int __fxstat(int,int,struct stat *);
static_assert(offsetof(struct stat,st_mode)==0x10 && offsetof(struct stat,st_uid)==0x18,
              "ARM glibc stat layout must match firmware");

// 仅引用原厂字符串访问器，不构造相机控制代理，不调用相机方法。
class Bus {
public:
    static const QString &farmService();
    static const QString &farmInterface();
    static const QString &farmPath();
    static const QString &cambodyService();
    static const QString &cambodyInterface();
    static const QString &cambodyPath();
};
namespace {
volatile sig_atomic_t stopRequested=0;
void stopObserver(int) { stopRequested=1; }
uint64_t monotonicUs() {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC,&value)!=0) return 0;
    return uint64_t(value.tv_sec)*1000000+uint64_t(value.tv_nsec)/1000;
}
bool writeAll(int fd,const char *data,size_t size) {
    while (size) {
        const ssize_t n=write(fd,data,size);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return false;
        data+=n; size-=size_t(n);
    }
    return true;
}
class Observer : public QObject {
public:
    explicit Observer(QObject *parent) : QObject(parent),bus(QDBusConnection::systemBus()) {
        struct stat directory;
        if (__lxstat(3,"/tmp/hbl-wireless-flash/observer",&directory)!=0) { std::perror("observer-directory-stat"); return; }
        if (!S_ISDIR(directory.st_mode) || directory.st_uid!=geteuid() || (directory.st_mode&077)!=0) {
            std::fprintf(stderr,"observer-directory-check mode=%o owner=%u self=%u\n",unsigned(directory.st_mode),unsigned(directory.st_uid),unsigned(geteuid())); return;
        }
        lockFd=open("/tmp/hbl-wireless-flash/observer/lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
        struct stat lockFile;
        if (lockFd<0 || __fxstat(3,lockFd,&lockFile)!=0 || !S_ISREG(lockFile.st_mode) ||
            lockFile.st_uid!=geteuid() || (lockFile.st_mode&077)!=0 || flock(lockFd,LOCK_EX|LOCK_NB)!=0) { std::perror("observer-lock-check"); return; }
        // 每次记录使用独立目录；已有记录时拒绝覆盖。
        logFd=open("/tmp/hbl-wireless-flash/observer/events.tsv",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
        if (logFd<0) { std::perror("observer-log-open"); return; }
        if (!writeAll(logFd,"elapsed_us\tevent\n",17)) return;
        start=monotonicUs();
        if (!start || !bus.isConnected() || !bus.interface()) { std::fputs("observer-bus-check\n",stderr); return; }
        const QString farm=Bus::farmService(),body=Bus::cambodyService();
        const QDBusReply<QString> farmOwner=bus.interface()->serviceOwner(farm);
        const QDBusReply<QString> bodyOwner=bus.interface()->serviceOwner(body);
        if (!farmOwner.isValid() || farmOwner.value().isEmpty() || !bodyOwner.isValid() || bodyOwner.value().isEmpty()) {
            std::fprintf(stderr,"observer-owner-check farm=%u body=%u\n",unsigned(farmOwner.isValid()&&!farmOwner.value().isEmpty()),unsigned(bodyOwner.isValid()&&!bodyOwner.value().isEmpty())); return;
        }
        watcher=new QDBusServiceWatcher(farm,bus,QDBusServiceWatcher::WatchForOwnerChange,this);
        if (body!=farm) watcher->addWatchedService(body);
        QObject::connect(watcher,&QDBusServiceWatcher::serviceOwnerChanged,this,
                         [this](const QString &,const QString &,const QString &) { finish("service_changed",25); });
        const char *names[]={"SensorExposureStart","SensorExposureDone","ReadyForExposure"};
        bool connected=true;
        for (unsigned i=0;i<3;++i) {
            farmReceivers[i].received=[this,i]() { receive(i+1); };
            connected=bus.connect(farm,Bus::farmPath(),Bus::farmInterface(),QString::fromLatin1(names[i]),
                                  &farmReceivers[i],SLOT(receive())) && connected;
        }
        bodyReceiver.received=[this]() { receive(0); };
        connected=bus.connect(body,Bus::cambodyPath(),Bus::cambodyInterface(),
                              QStringLiteral("exposure_seq_started"),&bodyReceiver,SLOT(receive(int))) && connected;
        const QDBusReply<QString> farmAfter=bus.interface()->serviceOwner(farm);
        const QDBusReply<QString> bodyAfter=bus.interface()->serviceOwner(body);
        if (!connected || !farmAfter.isValid() || !bodyAfter.isValid() ||
            farmAfter.value()!=farmOwner.value() || bodyAfter.value()!=bodyOwner.value()) { std::fputs("observer-binding-check\n",stderr); return; }
        valid=true;
        receive(4);
        if (!flush()) { valid=false; return; }
        heartbeat.setInterval(500);
        QObject::connect(&heartbeat,&QTimer::timeout,this,[this]() {
            if (stopRequested) { finish("stopped",0); return; }
            if (!bus.isConnected()) { finish("bus_disconnected",26); return; }
            if (!flush()) { finish("write_failed",27); return; }
            if (count==samples.size()) { finish("sample_limit",0); return; }
            const uint64_t now=monotonicUs();
            if (!now || now<start) { finish("clock_failed",28); return; }
            if (now-start>=300000000) finish("time_limit",0);
        });
        heartbeat.start();
    }
    ~Observer() override {
        if (logFd>=0) close(logFd);
        if (lockFd>=0) close(lockFd);
    }
    bool valid=false;
private:
    struct Sample { uint64_t elapsed; unsigned event; };
    QDBusConnection bus;
    QDBusServiceWatcher *watcher=nullptr;
    RfReceiver farmReceivers[3];
    RfIntReceiver bodyReceiver;
    QTimer heartbeat;
    std::array<Sample,512> samples;
    size_t count=0,written=0;
    uint64_t start=0;
    int lockFd=-1,logFd=-1;
    bool finished=false;
    void receive(unsigned event) {
        if (!valid || finished || count==samples.size()) return;
        const uint64_t now=monotonicUs();
        if (!now || now<start) { stopRequested=1; return; }
        // 信号参数（Tv）被丢弃；只保存同一进程时钟的通知到达时间和类型。
        samples[count++]={now-start,event};
    }
    bool flush() {
        static const char *names[]={"sequence_start","farm_start","farm_done","farm_ready","observer_ready"};
        while (written<count) {
            char line[96];
            const Sample &sample=samples[written];
            const int n=snprintf(line,sizeof(line),"%llu\t%s\n",static_cast<unsigned long long>(sample.elapsed),names[sample.event]);
            if (n<=0 || size_t(n)>=sizeof(line) || !writeAll(logFd,line,size_t(n))) return false;
            ++written;
        }
        return true;
    }
    void finish(const char *reason,int exitCode) {
        if (finished) return;
        finished=true; heartbeat.stop(); flush();
        char line[96];
        const int n=snprintf(line,sizeof(line),"# end\t%s\tsamples=%u\n",reason,unsigned(count));
        if (n>0 && size_t(n)<sizeof(line)) writeAll(logFd,line,size_t(n));
        QCoreApplication::exit(exitCode);
    }
};
}
int main(int argc,char **argv) {
    QCoreApplication application(argc,argv);
    if (argc==2 && !std::strcmp(argv[1],"--check-slots")) {
        unsigned count=0;
        RfReceiver empty;
        RfIntReceiver integer;
        empty.received=integer.received=[&count]() { ++count; };
        for (unsigned i=0;i<3;++i)
            if (!QMetaObject::invokeMethod(&empty,"receive",Qt::DirectConnection)) return 21;
        if (!QMetaObject::invokeMethod(&integer,"receive",Qt::DirectConnection,Q_ARG(int,123))) return 22;
        if (count!=4) return 23;
        std::puts("observer-slot-check=4 hardware-requests=0"); return 0;
    }
    if (argc!=1) return 64;
    signal(SIGTERM,stopObserver); signal(SIGINT,stopObserver);
    Observer observer(&application);
    if (!observer.valid) { std::fputs("observer-not-ready\n",stderr); return 20; }
    return application.exec();
}
