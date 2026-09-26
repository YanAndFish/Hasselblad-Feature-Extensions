/* 固定 X1D 1.25.0 原厂 testMethod 回显计时；无曝光、引闪、设置或串口入口。 */
#include <QtCore/qcoreapplication.h>
#include <QtCore/qjsonarray.h>
#include <QtCore/qjsondocument.h>
#include <QtCore/qjsonobject.h>
#include <QtCore/qxmlstream.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusmessage.h>
#include <QtDBus/qdbusreply.h>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>

static_assert(QT_VERSION==0x050501,"Audited Qt 5.5.1 required");
static_assert(sizeof(void*)==4,"Audited ARM32 ABI required");
static constexpr unsigned Trials=16;
static const char *ResultPath="/tmp/hbl-wireless-flash/farm-rtt.json";

static uint64_t nowNs() {
    timespec value={};
    if (clock_gettime(CLOCK_MONOTONIC,&value) || value.tv_sec<0 || value.tv_nsec<0 || value.tv_nsec>=1000000000) return 0;
    return uint64_t(value.tv_sec)*1000000000u+uint64_t(value.tv_nsec);
}
static bool validReply(const QDBusMessage &reply) {
    const auto values=reply.arguments();
    return reply.type()==QDBusMessage::ReplyMessage && values.size()==1 &&
           values[0].userType()==QMetaType::Bool && values[0].toBool();
}
static QDBusMessage request(const QString &owner,const QString &interface,const QString &method) {
    auto message=QDBusMessage::createMethodCall(owner,QStringLiteral("/farm"),interface,method);
    message.setAutoStartService(false);
    return message;
}
static bool save(int fd,const QJsonObject &report) {
    const QByteArray data=QJsonDocument(report).toJson(QJsonDocument::Compact);
    int offset=0;
    while (offset<data.size()) {
        const ssize_t written=write(fd,data.constData()+offset,size_t(data.size()-offset));
        if (written<0 && errno==EINTR) continue;
        if (written<=0) { close(fd); return false; }
        offset+=int(written);
    }
    return close(fd)==0;
}
int main(int argc,char **argv) {
    if (argc!=2) return 60;
    const bool check=!std::strcmp(argv[1],"--check");
    const bool describe=!std::strcmp(argv[1],"--describe");
    const bool measure=!std::strcmp(argv[1],"--measure");
    if (!check && !describe && !measure) return 60;
    QCoreApplication app(argc,argv);
    if (check) {
        auto call=QDBusMessage::createMethodCall(QStringLiteral("com.example.test"),QStringLiteral("/"),QStringLiteral("com.example.test"),QStringLiteral("check"));
        if (!validReply(call.createReply(QVariant(true))) || validReply(call.createReply(QVariant(false))) ||
            validReply(call.createReply(QVariant(1))) || validReply(call.createReply()) ||
            validReply(call.createErrorReply(QStringLiteral("com.example.Error"),QStringLiteral("test")))) return 61;
        const uint64_t a=nowNs(),b=nowNs();
        if (!a || b<a) return 61;
        std::puts("farm-rtt-selftest=5 hardware-requests=0");
        return 0;
    }
    const QDBusConnection bus=QDBusConnection::systemBus();
    if (!bus.isConnected() || !bus.interface()) return 62;
    const QDBusReply<QString> initial=bus.interface()->serviceOwner(QStringLiteral("com.hasselblad.farm"));
    if (!initial.isValid() || !initial.value().startsWith(QLatin1Char(':'))) return 62;
    const QString owner=initial.value();
    if (describe) {
        const auto reply=bus.call(request(owner,QStringLiteral("org.freedesktop.DBus.Introspectable"),QStringLiteral("Introspect")),QDBus::Block,2000);
        if (reply.type()!=QDBusMessage::ReplyMessage || reply.arguments().size()!=1 || reply.arguments()[0].userType()!=QMetaType::QString) return 63;
        QXmlStreamReader xml(reply.arguments()[0].toString());
        bool interface=false,method=false,found=false;
        QByteArray signature;
        while (!xml.atEnd()) {
            xml.readNext();
            if (xml.isStartElement() && xml.name()==QLatin1String("interface")) interface=xml.attributes().value(QLatin1String("name"))==QLatin1String("com.hasselblad.linkstatus");
            if (xml.isStartElement() && xml.name()==QLatin1String("method")) method=interface && xml.attributes().value(QLatin1String("name"))==QLatin1String("testMethod");
            if (method && xml.isStartElement() && xml.name()==QLatin1String("arg")) {
                signature+=xml.attributes().value(QLatin1String("direction")).toString().toUtf8()+":"+xml.attributes().value(QLatin1String("type")).toString().toUtf8()+";";
            }
            if (method && xml.isEndElement() && xml.name()==QLatin1String("method")) { found=true; method=false; }
            if (xml.isEndElement() && xml.name()==QLatin1String("interface")) interface=false;
        }
        if (xml.hasError() || !found || signature.size()>100) return 63;
        std::printf("farm-testMethod=%s\n",signature.constData());
        return signature=="out:b;in:i;" || signature=="in:i;out:b;" ? 0 : 63;
    }
    const int fd=open(ResultPath,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if (fd<0) return 64;
    QJsonArray samples;
    uint64_t intervals[Trials]={};
    unsigned attempted=0,accepted=0;
    int error=0;
    for (unsigned i=0;i<Trials;++i) {
        auto message=request(owner,QStringLiteral("com.hasselblad.linkstatus"),QStringLiteral("testMethod"));
        message.setArguments(QList<QVariant>()<<QVariant(0));
        const uint64_t before=nowNs();
        if (!before) { error=65; break; }
        ++attempted;
        const auto reply=bus.call(message,QDBus::Block,2000);
        const uint64_t after=nowNs();
        const bool ok=after>=before && validReply(reply);
        QJsonObject row;
        row.insert(QStringLiteral("index"),int(i));
        row.insert(QStringLiteral("rtt_ns"),after>=before ? double(after-before) : -1.0);
        row.insert(QStringLiteral("echo_verified"),ok);
        row.insert(QStringLiteral("reply_type"),int(reply.type()));
        if (reply.type()==QDBusMessage::ErrorMessage) row.insert(QStringLiteral("error_name"),reply.errorName());
        samples.append(row);
        if (!ok) { error=66; break; }
        intervals[accepted++]=after-before;
        if (i+1<Trials) {
            timespec pause={0,100000000};
            while (nanosleep(&pause,&pause) && errno==EINTR) {}
        }
    }
    const QDBusReply<QString> final=bus.interface()->serviceOwner(QStringLiteral("com.hasselblad.farm"));
    const bool sameOwner=final.isValid() && final.value()==owner;
    if (!sameOwner) error=67;
    QJsonObject report;
    report.insert(QStringLiteral("attempted"),int(attempted));
    report.insert(QStringLiteral("accepted"),int(accepted));
    report.insert(QStringLiteral("samples"),samples);
    report.insert(QStringLiteral("same_service_owner"),sameOwner);
    report.insert(QStringLiteral("clock"),QStringLiteral("CLOCK_MONOTONIC"));
    report.insert(QStringLiteral("scope"),QStringLiteral("Linux DBus call -> FARM fixed 255-byte echo -> Linux DBus reply"));
    report.insert(QStringLiteral("reply_payload_bytes"),255);
    report.insert(QStringLiteral("single_direction_measured"),false);
    report.insert(QStringLiteral("physical_flash_measured"),false);
    report.insert(QStringLiteral("error"),error);
    if (accepted) {
        for (unsigned i=1;i<accepted;++i) {
            const uint64_t value=intervals[i];
            unsigned j=i;
            while (j && intervals[j-1]>value) { intervals[j]=intervals[j-1]; --j; }
            intervals[j]=value;
        }
        report.insert(QStringLiteral("min_ns"),double(intervals[0]));
        report.insert(QStringLiteral("median_ns"),double(intervals[accepted/2]));
        report.insert(QStringLiteral("max_ns"),double(intervals[accepted-1]));
    }
    if (!save(fd,report)) return 68;
    if (error) { std::printf("farm-rtt-failed attempted=%u accepted=%u reason=%d\n",attempted,accepted,error); return error; }
    std::printf("farm-rtt count=%u min_us=%.3f median_us=%.3f max_us=%.3f\n",accepted,
                double(intervals[0])/1000.0,double(intervals[accepted/2])/1000.0,double(intervals[accepted-1])/1000.0);
    return 0;
}
