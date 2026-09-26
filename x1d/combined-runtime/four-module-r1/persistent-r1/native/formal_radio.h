#ifndef HBL_FORMAL_RADIO_H
#define HBL_FORMAL_RADIO_H
#include "formal_prepared_request.h"
#ifdef HBL_FORMAL_RADIO_TEST_PLATFORM
#include HBL_FORMAL_RADIO_TEST_PLATFORM
#else
#include "mechanical_direct_dispatch.h"
#include <QtCore/qobject.h>
#include <QtCore/qprocess.h>
#include <QtCore/qtimer.h>
#include <QtCore/qsocketnotifier.h>
#include <sys/socket.h>
#include <linux/netlink.h>
#include <net/if.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <functional>
#endif

/* QObject 所在线程拥有所有状态；仅专用线程执行预编码同步发送。
 * bool 返回值仅表示是否接受操作；结果总在后续 Qt turn 通知。
 * 功率批次与恢复同步波形由 worker 编排，此层没有隐含功率队列。
 */
class FormalRadio : public QObject {
public:
    enum Operation { Open, Select, Power, Fire, Close, Batch };
    bool batchEnabled=false;
    explicit FormalRadio(QObject *parent=nullptr) : QObject(parent) {
        QProcessEnvironment env=QProcessEnvironment::systemEnvironment();
        env.remove(QStringLiteral("LD_PRELOAD"));
        env.remove(QStringLiteral("HBL_RF_ENABLE_PLUGIN"));
        process.setProcessEnvironment(env);
        process.setProcessChannelMode(QProcess::SeparateChannels);
        watchdog.setSingleShot(true);
        QObject::connect(&watchdog,&QTimer::timeout,this,[this]() { timedOut(); });
        QObject::connect(&process,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),
                         this,[this](int code,QProcess::ExitStatus status) { processFinished(code,status); });
        QObject::connect(&process,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),
                         this,[this](QProcess::ProcessError why) {
            if (why==QProcess::FailedToStart) processFinished(-1,QProcess::CrashExit);
        });
        if (dispatch.valid()) {
            dispatchNotifier=new QSocketNotifier(dispatch.completionFd(),QSocketNotifier::Read,this);
            QObject::connect(dispatchNotifier,&QSocketNotifier::activated,this,[this](int) {
                finishDispatch(dispatch.take());
            });
        }
    }
    ~FormalRadio() override {
        completed=nullptr; changed=nullptr;
        dispatch.cancel(); watchdog.stop();
        /* 析构的有限兜底仅释放本模块曾尝试持有的 MAC，不重新发送功率/同步。 */
        stage=Idle;
        if (process.state()!=QProcess::NotRunning) {
            process.kill(); process.waitForFinished(200);
        }
        closeTransport();
        delete dispatchNotifier;
        if (held) {
            QProcess cleanup;
            cleanup.setProcessEnvironment(process.processEnvironment());
            cleanup.start(QStringLiteral("/usr/bin/wl"),QStringList()<<QStringLiteral("phyreg")
                          <<QStringLiteral("27")<<QStringLiteral("b"));
            if (!cleanup.waitForFinished(500)) { cleanup.kill(); cleanup.waitForFinished(200); }
        }
    }
    bool valid() const { return dispatch.valid(); }
    bool open(unsigned channel=5,unsigned id=5) {
        if (!valid() || busy || held || closeWanted || !hbl_formal_config_valid(channel,id)) return false;
        configuredChannel=channel; configuredId=id;
        cleanupAttempted=false; cleanupFailed=false;
        selectedIndex=HBL_FORMAL_WAVES; error.clear();
        accept(Open); stage=Starting;
        QTimer::singleShot(0,this,[this]() {
            if (stage!=Starting || activeOperation!=Open) return;
            if (closeWanted) { finish(false); return; }
            if (!openTransport()) { fail(QStringLiteral("无线驱动通道不可用")); return; }
            send(Family,0);
        });
        return true;
    }
    bool select(unsigned waveIndex) {
        if (!canOperate() || waveIndex>=HBL_FORMAL_WAVES) return false;
        accept(Select); desiredIndex=waveIndex;
        send(Preparing,waveIndex==HBL_FORMAL_FIRE_INDEX ? 14 : 512+waveIndex);
        return true;
    }
    bool sendPower() {
        if (!canOperate() || !ready || selectedIndex>=HBL_FORMAL_CONTROL_WAVES) return false;
        accept(Power); send(PowerReply,48); return true;
    }
    bool sendBatch(unsigned mask,const unsigned indices[16]) {
        if(!batchEnabled || !canOperate() || !indices || mask>65535) return false;
        for(unsigned i=0;i<16;++i) if(mask&(1u<<i)) {
            if(indices[i]>=HBL_FORMAL_POWER_WAVES || indices[i]/HBL_FORMAL_VALUES!=i) return false;
        }
        batchMask=mask;batchPosition=0;
        for(unsigned i=0;i<16;++i) batchIndices[i]=indices[i];
        accept(Batch);send(BatchBegin,12000);return true;
    }
    bool fire(uint64_t absoluteUs=0) {
        if (!canOperate() || !ready || selectedIndex!=HBL_FORMAL_FIRE_INDEX || !request.ready) return false;
        accept(Fire); stage=FireReply; dispatchSubmitted=false;
        if (!formal_consume_request(&request,sequence)) {
            fail(QStringLiteral("同步请求已失效")); return true;
        }
        sequence=request.sequence;
        if (!absoluteUs) absoluteUs=nowUs();
        sockaddr_nl peer={}; peer.nl_family=AF_NETLINK;
        notifier->setEnabled(false);
        if (!dispatch.schedule(fd,request.bytes,request.size,
                               reinterpret_cast<const sockaddr *>(&peer),sizeof(peer),absoluteUs))
            fail(QStringLiteral("专用同步线程未接受截止点"));
        return true;
    }
    MechanicalDirectDispatch::Result cancelPending() {
        if (stage!=FireReply) return MechanicalDirectDispatch::Empty;
        if (dispatchSubmitted) return MechanicalDirectDispatch::Submitted;
        const auto result=dispatch.cancel();
        if (result==MechanicalDirectDispatch::Cancelled) {
            if (notifier) notifier->setEnabled(true);
            if (!prepareNextFire()) { fail(QStringLiteral("取消后同步请求失效")); return MechanicalDirectDispatch::Failed; }
            finish(false,true);
        } else if (result==MechanicalDirectDispatch::Submitted) finishDispatch(result);
        else if (result==MechanicalDirectDispatch::Failed) fail(QStringLiteral("专用同步线程提交失败"));
        return result;
    }
    void close() {
        closeWanted=true; ready=false; request.ready=0;
        publish();
        if (stage==FireReply) cancelPending();
        if (!busy) startClose();
    }

    bool ready=false,busy=false,held=false;
    unsigned selectedIndex=HBL_FORMAL_WAVES;
    QString error;
    std::function<void(Operation,bool)> completed;
    std::function<void()> changed;
private:
    enum Stage { Idle,Starting,Family,Marker,InitialRelease,ChannelSet,GainSet,GainRead,Hold,Configure,ConfigChannelRead,ConfigIdRead,
                 Preparing,HashLow,HashHigh,ReadyRead,IndexRead,PowerReply,FireReply,
                 Releasing,ReleaseCli,Finishing,BatchBegin,BatchItem,BatchCommit,BatchReply } stage=Idle;
    unsigned batchMask=0,batchPosition=0,batchIndices[16]={};
    void sendNextBatchItem() {
        while(batchPosition<16 && !(batchMask&(1u<<batchPosition))) ++batchPosition;
        if(batchPosition==16) send(BatchCommit,12001);
        else send(BatchItem,16384+batchIndices[batchPosition++]);
    }
    Operation activeOperation=Open;
    int fd=-1;
    uint32_t port=0,sequence=0,ifindex=0,hashLow=0,hashHigh=0,chipReady=0;
    uint16_t family=0;
    unsigned desiredIndex=HBL_FORMAL_FIRE_INDEX;
    unsigned configuredChannel=5,configuredId=5;
    bool closeWanted=false,cleanupAttempted=false,cleanupFailed=false;
    bool dispatchSubmitted=false,changeQueued=false,processTimedOut=false;
    QProcess process;
    QTimer watchdog;
    QSocketNotifier *notifier=nullptr,*dispatchNotifier=nullptr;
    MechanicalDirectDispatch dispatch;
    FormalPreparedRequest request={};

    static uint64_t nowUs() {
        timespec at={};
        if (clock_gettime(CLOCK_MONOTONIC,&at) || at.tv_sec<0 || at.tv_nsec<0) return 0;
        return uint64_t(at.tv_sec)*1000000u+uint64_t(at.tv_nsec)/1000u;
    }
    bool canOperate() const { return !busy && !closeWanted && held && fd>=0 && family>=17 && valid(); }
    void publish() {
        if (changeQueued) return;
        changeQueued=true;
        QTimer::singleShot(0,this,[this]() {
            changeQueued=false; const auto callback=changed; if (callback) callback();
        });
    }
    void accept(Operation next) {
        activeOperation=next; busy=true; ready=false;
        if (next!=Fire) request.ready=0;
        publish();
    }
    bool prepareNextFire() {
        if (selectedIndex!=HBL_FORMAL_FIRE_INDEX) { request.ready=0; return true; }
        return formal_prepare_request(&request,family,sequence,port,ifindex,selectedIndex)!=0;
    }
    void finish(bool ok,bool cancelled=false) {
        watchdog.stop();
        const Operation done=activeOperation;
        stage=Finishing;
        ready=(ok || cancelled) && !closeWanted && held && selectedIndex<HBL_FORMAL_WAVES;
        /* 保持 busy 直到结果通知，防止旧完成通知落在新操作之后。 */
        QTimer::singleShot(0,this,[this,done,ok]() {
            if (stage!=Finishing) return;
            stage=Idle; busy=false;
            if (done==Close) closeWanted=false;
            publish();
            if (closeWanted) QTimer::singleShot(0,this,[this]() { if (closeWanted && !busy) startClose(); });
            /* 回调可以销毁拥有者，调用后不再访问成员。 */
            const auto callback=completed;
            if (callback) callback(done,ok);
        });
    }
    void fail(const QString &why) {
        if (stage==Idle || stage==Finishing) return;
        error=why; ready=false; request.ready=0;
        dispatch.cancel(); watchdog.stop();
        if (notifier) notifier->setEnabled(true);
        if (activeOperation==Close) {
            cleanupFailed=true; closeTransport(); finish(false); return;
        }
        closeWanted=true; finish(false);
    }
    bool openTransport() {
        ifindex=if_nametoindex("wlp1s0");
        if (!ifindex) return false;
        sockaddr_nl local={}; socklen_t length=sizeof(local);
        fd=socket(AF_NETLINK,SOCK_RAW|SOCK_NONBLOCK|SOCK_CLOEXEC,NETLINK_GENERIC);
        if (fd<0) return false;
        local.nl_family=AF_NETLINK;
        if (bind(fd,reinterpret_cast<sockaddr *>(&local),sizeof(local)) ||
            getsockname(fd,reinterpret_cast<sockaddr *>(&local),&length) ||
            length!=sizeof(local) || local.nl_family!=AF_NETLINK || !local.nl_pid) {
            closeTransport(); return false;
        }
        port=local.nl_pid;
        notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int) { receive(); });
        return true;
    }
    void closeTransport() {
        watchdog.stop(); dispatch.cancel(); request.ready=0;
        if (notifier) { notifier->setEnabled(false); delete notifier; notifier=nullptr; }
        if (fd>=0) { ::close(fd); fd=-1; }
        family=0; port=0; ifindex=0;
    }
    bool send(Stage next,uint32_t selector) {
        stage=next;
        if (sequence==UINT32_MAX) { fail(QStringLiteral("驱动请求序列耗尽")); return false; }
        uint8_t bytes[128]; sockaddr_nl peer={}; peer.nl_family=AF_NETLINK;
        const size_t size=next==Family ? rf_nl_family_request(bytes,sizeof(bytes),++sequence,port) :
            formal_nl_register_request(bytes,sizeof(bytes),family,++sequence,port,ifindex,selector);
        if (!size || fd<0 || sendto(fd,bytes,size,MSG_DONTWAIT|MSG_NOSIGNAL,
                                    reinterpret_cast<sockaddr *>(&peer),sizeof(peer))!=ssize_t(size)) {
            fail(QStringLiteral("驱动请求未完整提交")); return false;
        }
        watchdog.start(1000); return true;
    }
    void startProcess(Stage next) {
        stage=next; processTimedOut=false;
        QStringList args;
        if (next==ChannelSet) args<<QStringLiteral("chanspec")<<QString::number(hbl_formal_chanspec(configuredChannel)&255)+QStringLiteral("/20");
        else if (next==GainSet) args<<QStringLiteral("phy_txpwrindex")<<QStringLiteral("10")<<QStringLiteral("10");
        else if (next==GainRead) args<<QStringLiteral("phy_txpwrindex");
        else args<<QStringLiteral("phyreg")<<QStringLiteral("27")<<QStringLiteral("b");
        watchdog.start(1000);
        process.start(QStringLiteral("/usr/bin/wl"),args);
    }
    void startClose() {
        if (busy) return;
        accept(Close);
        if (!held) { closeTransport(); selectedIndex=HBL_FORMAL_WAVES; finish(true); return; }
        if (cleanupAttempted || cleanupFailed) {
            closeTransport(); finish(false); return;
        }
        cleanupAttempted=true;
        if (fd>=0 && family>=17 && sequence!=UINT32_MAX) send(Releasing,27);
        else startProcess(ReleaseCli);
    }
    void released() {
        held=false; selectedIndex=HBL_FORMAL_WAVES;
        closeTransport(); finish(true);
    }
    void timedOut() {
        if (stage==ChannelSet || stage==GainSet || stage==GainRead || stage==ReleaseCli) {
            const Stage waiting=stage;
            processTimedOut=true; process.kill(); process.waitForFinished(100);
            if (stage!=waiting) return;
        }
        fail(QStringLiteral("无线驱动响应超时"));
    }
    void processFinished(int code,QProcess::ExitStatus status) {
        const Stage done=stage;
        if (done!=ChannelSet && done!=GainSet && done!=GainRead && done!=ReleaseCli) return;
        watchdog.stop();
        const QByteArray output=process.readAllStandardOutput().trimmed();
        process.readAllStandardError();
        const bool exited=code==0 && status==QProcess::NormalExit && !processTimedOut;
        if (done==ReleaseCli) {
            bool parsed=false; const uint value=output.toUInt(&parsed,16);
            if (exited && parsed && value==1) released();
            else fail(QStringLiteral("无线释放未获确认"));
            return;
        }
        if (closeWanted) { finish(false); return; }
        if (done==ChannelSet) {
            // X1D 1.25.0 的 wl 成功时返回 "Chanspec set to 0x1002"，并非空输出。
            const QByteArray prefix("Chanspec set to ");
            bool parsed=false;
            const uint reported=output.mid(prefix.size()).toUInt(&parsed,16);
            const bool confirmed=output.isEmpty() || (output.startsWith(prefix) && parsed && reported==hbl_formal_chanspec(configuredChannel));
            if (!exited || !confirmed) { fail(QStringLiteral("无线频道设置失败")); return; }
            startProcess(GainSet); return;
        }
        if (done==GainSet) {
            if (!exited || !output.isEmpty()) { fail(QStringLiteral("固定射频增益设置失败")); return; }
            startProcess(GainRead); return;
        }
        const QByteArray prefix("txpwrindex for core{0...3}:");
        const QList<QByteArray> fields=output.mid(prefix.size()).simplified().split(' ');
        if (!exited || !output.startsWith(prefix) || fields.size()!=4 ||
            fields[0]!="10" || fields[1]!="10" || fields[2]!="0" || fields[3]!="0") {
            fail(QStringLiteral("固定射频增益读回不符")); return;
        }
        held=true; // hold 即使超时，也必须经过有限释放。
        send(Hold,26);
    }
    void finishDispatch(MechanicalDirectDispatch::Result result) {
        if (stage!=FireReply || result==MechanicalDirectDispatch::Empty || dispatchSubmitted) return;
        if (result!=MechanicalDirectDispatch::Submitted) { fail(QStringLiteral("同步请求未完整提交")); return; }
        dispatchSubmitted=true;
        if (notifier) notifier->setEnabled(true);
        watchdog.start(1000);
    }
    void received(uint32_t value) {
        watchdog.stop();
        const Stage done=stage;
        if (done==Releasing) {
            if (value==1) released(); else fail(QStringLiteral("无线释放被拒绝"));
            return;
        }
        if (done==InitialRelease && value==1) held=false;
        if (closeWanted) { finish(false); return; }
        switch (done) {
        case Family: family=uint16_t(value); send(Marker,0); break;
        case Marker:
            if (value!=(batchEnabled ? 0x5855u : 0x5854u)) fail(QStringLiteral("正式无线固件版本不符"));
            else send(InitialRelease,27);
            break;
        case InitialRelease:
            if (value!=1) fail(QStringLiteral("无线旧准备未释放"));
            else startProcess(ChannelSet);
            break;
        case Hold:
            if (value!=1) fail(QStringLiteral("无线占用被拒绝"));
            else send(Configure,hbl_formal_config_selector(configuredChannel,configuredId));
            break;
        case Configure:
            if (value!=1) fail(QStringLiteral("频道与芯片配置不符"));
            else send(ConfigChannelRead,19);
            break;
        case ConfigChannelRead:
            if (value!=configuredChannel) fail(QStringLiteral("无线频道读回不符"));
            else send(ConfigIdRead,20);
            break;
        case ConfigIdRead:
            if (value!=configuredId) fail(QStringLiteral("无线 ID 读回不符"));
            else { desiredIndex=HBL_FORMAL_FIRE_INDEX; send(Preparing,14); }
            break;
        case Preparing:
            if (value!=1) fail(QStringLiteral("芯片波形准备失败"));
            else send(HashLow,15);
            break;
        case HashLow: hashLow=value; send(HashHigh,16); break;
        case HashHigh: hashHigh=value; send(ReadyRead,17); break;
        case ReadyRead: chipReady=value; send(IndexRead,18); break;
        case IndexRead:
            if (!formal_selection_verified_config(desiredIndex,hashLow,hashHigh,chipReady,value,configuredChannel,configuredId))
                fail(QStringLiteral("波形哈希或就绪索引不符"));
            else {
                selectedIndex=desiredIndex;
                if (!prepareNextFire()) fail(QStringLiteral("无法预编码同步请求"));
                else finish(true);
            }
            break;
        case PowerReply: case FireReply:
            if (value!=1) fail(QStringLiteral("芯片发送被拒绝"));
            else if (!prepareNextFire()) fail(QStringLiteral("无法预编码后续同步请求"));
            else finish(true);
            break;
        case BatchBegin:case BatchItem:
            if(value!=1) fail(QStringLiteral("参数批次暂存失败"));
            else sendNextBatchItem();
            break;
        case BatchCommit:
            if(value!=1) fail(QStringLiteral("参数批次提交失败"));
            else send(BatchReply,12002);
            break;
        case BatchReply:
            if(value!=1) fail(QStringLiteral("参数批次执行失败"));
            else { desiredIndex=HBL_FORMAL_FIRE_INDEX;send(HashLow,15); }
            break;
        default: fail(QStringLiteral("无线回复状态不符")); break;
        }
    }
    void receive() {
        for (unsigned count=0;count<32 && fd>=0;++count) {
            uint8_t bytes[4096]; sockaddr_nl peer={}; iovec io={bytes,sizeof(bytes)}; msghdr message={};
            message.msg_name=&peer; message.msg_namelen=sizeof(peer); message.msg_iov=&io; message.msg_iovlen=1;
            const ssize_t size=recvmsg(fd,&message,MSG_DONTWAIT);
            if (size<0 && (errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR)) return;
            if (size<=0 || (message.msg_flags&MSG_TRUNC) || message.msg_namelen!=sizeof(peer) ||
                peer.nl_family!=AF_NETLINK || peer.nl_pid) { fail(QStringLiteral("驱动回复来源或长度无效")); return; }
            size_t offset=0;
            while (offset<size_t(size)) {
                const size_t remain=size_t(size)-offset;
                if (remain<16) { fail(QStringLiteral("驱动回复被截断")); return; }
                const size_t length=rf_le32(bytes+offset);
                if (length<16 || length>remain || rf_align4(length)>remain) {
                    fail(QStringLiteral("驱动回复长度无效")); return;
                }
                if (stage!=Idle && stage!=Finishing && stage!=Starting && stage!=ChannelSet && stage!=GainSet && stage!=GainRead && stage!=ReleaseCli) {
                    uint32_t value=0; int32_t driverError=0;
                    const int result=rf_nl_one_reply(bytes+offset,length,sequence,port,family,
                        stage==Family ? RF_NL_FAMILY : RF_NL_REGISTER,&value,&driverError);
                    if (result<0) { fail(QStringLiteral("驱动拒绝或回复不完整")); return; }
                    if (result==RF_NL_DATA) received(value);
                }
                offset+=rf_align4(length);
            }
        }
    }
};
#endif
