#ifndef HBL_NETLINK_RADIO_H
#define HBL_NETLINK_RADIO_H
#include "rf_netlink_wire.h"
#include <QtCore/qsocketnotifier.h>
#include <sys/socket.h>
#include <linux/netlink.h>
#include <net/if.h>
#include <unistd.h>
#include <errno.h>

class NetlinkRadio : public QObject {
public:
    explicit NetlinkRadio(QObject *parent) : QObject(parent) {
        watchdog.setSingleShot(true);
        QObject::connect(&watchdog,&QTimer::timeout,this,[this]() { fail(QStringLiteral("驱动响应超时")); });
    }
    ~NetlinkRadio() override { closeChannel(); }
    std::function<void(bool)> prepared;
    std::function<void(bool)> fired;
    QString error;
    bool ready=false;
    bool prepare() {
        if (operation!=None) return false;
        ready=false;
        const unsigned currentIndex=if_nametoindex("wlp1s0");
        if (!currentIndex) { error=QStringLiteral("无线接口不可用"); return false; }
        if (fd>=0 && currentIndex!=ifindex) closeChannel();
        ifindex=currentIndex;
        if (fd<0) {
            sockaddr_nl local={}; socklen_t size=sizeof(local);
            fd=socket(AF_NETLINK,SOCK_RAW|SOCK_NONBLOCK|SOCK_CLOEXEC,NETLINK_GENERIC);
            if (fd<0) { error=QStringLiteral("无法打开驱动通道"); return false; }
            local.nl_family=AF_NETLINK;
            if (bind(fd,reinterpret_cast<sockaddr *>(&local),sizeof(local)) ||
                getsockname(fd,reinterpret_cast<sockaddr *>(&local),&size)) {
                closeChannel(); error=QStringLiteral("无法绑定驱动通道"); return false;
            }
            port=local.nl_pid;
            notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
            QObject::connect(notifier,&QSocketNotifier::activated,
                             this,[this](int) { receive(); });
        }
        return send(family ? Marker : Family);
    }
    bool fire() {
        if (!ready || operation!=None || fd<0) return false;
        ready=false;
        return send(Fire);
    }
    void invalidate() { ready=false; }
private:
    enum Operation { None,Family,Marker,Fire } operation=None;
    int fd=-1;
    uint32_t port=0,sequence=0,ifindex=0;
    uint16_t family=0;
    QSocketNotifier *notifier=nullptr;
    QTimer watchdog;
    void closeChannel() {
        watchdog.stop(); operation=None; ready=false; family=0;
        if (notifier) { notifier->setEnabled(false); delete notifier; notifier=nullptr; }
        if (fd>=0) { close(fd); fd=-1; }
    }
    bool send(Operation next) {
        uint8_t bytes[128]; sockaddr_nl peer={}; size_t size;
        if (++sequence==0) { closeChannel(); error=QStringLiteral("驱动序列耗尽"); return false; }
        size=next==Family ? rf_nl_family_request(bytes,sizeof(bytes),sequence,port) :
             rf_nl_register_request(bytes,sizeof(bytes),family,sequence,port,ifindex,next==Fire ? 40 : 0);
        peer.nl_family=AF_NETLINK;
        if (!size || sendto(fd,bytes,size,MSG_DONTWAIT,reinterpret_cast<sockaddr *>(&peer),sizeof(peer))!=static_cast<ssize_t>(size)) {
            closeChannel(); error=QStringLiteral("驱动请求未提交"); return false;
        }
        operation=next; watchdog.start(1000); return true;
    }
    void fail(const QString &why) {
        const bool wasFire=operation==Fire;
        error=why; closeChannel();
        if (wasFire) { if (fired) fired(false); }
        else if (prepared) prepared(false);
    }
    void received(uint32_t value) {
        watchdog.stop(); const Operation done=operation; operation=None;
        if (done==Family) {
            family=static_cast<uint16_t>(value);
            if (!send(Marker)) { if (prepared) prepared(false); }
        } else if (done==Marker) {
            ready=value==0x584e;
            if (!ready) { error=QStringLiteral("驱动读回版本不符"); closeChannel(); }
            if (prepared) prepared(ready);
        } else if (done==Fire) {
            ready=value==1;
            if (!ready) error=QStringLiteral("快速发射被固件拒绝");
            if (fired) fired(ready);
        }
    }
    void receive() {
        for (unsigned count=0;count<32 && fd>=0;++count) {
            uint8_t bytes[4096]; sockaddr_nl peer={}; iovec io={bytes,sizeof(bytes)}; msghdr msg={};
            msg.msg_name=&peer; msg.msg_namelen=sizeof(peer); msg.msg_iov=&io; msg.msg_iovlen=1;
            const ssize_t size=recvmsg(fd,&msg,MSG_DONTWAIT);
            if (size<0 && (errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR)) return;
            if (size<=0 || (msg.msg_flags&MSG_TRUNC) || peer.nl_family!=AF_NETLINK || peer.nl_pid) {
                fail(QStringLiteral("驱动回复无效")); return;
            }
            size_t offset=0;
            while (offset<static_cast<size_t>(size)) {
                const size_t remain=static_cast<size_t>(size)-offset;
                if (remain<16) { fail(QStringLiteral("驱动回复被截断")); return; }
                const size_t length=rf_le32(bytes+offset);
                if (length<16 || length>remain || rf_align4(length)>remain) { fail(QStringLiteral("驱动回复长度无效")); return; }
                if (operation!=None) {
                    uint32_t value=0; int32_t driverError=0;
                    const int result=rf_nl_one_reply(bytes+offset,length,sequence,port,family,
                         operation==Family ? RF_NL_FAMILY : RF_NL_REGISTER,&value,&driverError);
                    if (result<0) { fail(QStringLiteral("驱动拒绝或回复不完整")); return; }
                    if (result==RF_NL_DATA) received(value);
                }
                offset+=rf_align4(length);
            }
        }
    }
};
#endif
