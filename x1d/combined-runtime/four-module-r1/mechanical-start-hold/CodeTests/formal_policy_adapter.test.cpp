/* 运行真实 FormalPolicy、FormalRadio 和 worker 共用的取消转接函数。
 * 替身只替换 Qt 排队、驱动字节传输和进程；不打开真实设备或进程。 */
#include "formal_radio_fake_platform.h"
#define HBL_FORMAL_RADIO_TEST_PLATFORM "formal_radio_fake_platform.h"
#define private public
#include "../native/formal_radio.h"
#undef private
#include "../native/formal_policy.h"
namespace io=formal_test;
static unsigned checks=0,deviceIndex=HBL_FORMAL_FIRE_INDEX,deviceChannel=5,deviceId=5;
static std::map<unsigned,uint32_t> overrideValues;
#define CHECK(value) do { ++checks;if(!(value)) throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#value); } while(0)
using Policy=FormalPolicy;
static uint64_t now() { return ++io::clockUs; }
static unsigned sentCount(unsigned selector) { return unsigned(std::count(io::selectors.begin(),io::selectors.end(),selector)); }
static std::vector<uint8_t> reply(const std::vector<uint8_t> &request) {
    uint8_t out[128]={},word[8]={},nested[64]={};
    const bool family=rf_le16(request.data()+4)==16;
    size_t used=rf_nl_begin(out,sizeof(out),family ? 16:35,rf_le32(request.data()+8),99,family ? 1:103);
    if(family) {
        rf_put16(word,35);rf_nl_add(out,sizeof(out),&used,1,word,2);rf_nl_add(out,sizeof(out),&used,2,"nl80211",8);
    } else {
        const unsigned selector=rf_le32(request.data()+68);
        if(selector==14) deviceIndex=HBL_FORMAL_FIRE_INDEX;
        if(selector>=512 && selector<512+HBL_FORMAL_CONTROL_WAVES) deviceIndex=selector-512;
        if(selector>=HBL_FORMAL_CONFIG_BASE && selector<HBL_FORMAL_CONFIG_BASE+HBL_FORMAL_CONFIG_COUNT) {
            deviceChannel=(selector-HBL_FORMAL_CONFIG_BASE)/100+1;deviceId=(selector-HBL_FORMAL_CONFIG_BASE)%100;
        }
        uint32_t hash=0;
        if(selector==15 || selector==16) hbl_formal_wave_hash(&hash,deviceIndex,deviceChannel,deviceId,hbl_formal_lut);
        uint32_t value=1;
        if(selector==19) value=deviceChannel;
        if(selector==20) value=deviceId;
        if(selector==0) value=0x5854;
        if(selector==15) value=hash&0xffff;
        if(selector==16) value=hash>>16;
        if(selector==18) value=deviceIndex;
        if(overrideValues.count(selector)) value=overrideValues[selector];
        rf_put16(nested,6);rf_put16(nested+2,1);rf_put16(nested+4,4);
        rf_put16(nested+8,8);rf_put16(nested+10,2);rf_put32(nested+12,value);
        rf_nl_add(out,sizeof(out),&used,197,nested,16);
    }
    return std::vector<uint8_t>(out,out+used);
}
class AdapterFixture {
public:
    Policy policy;FormalRadio radio;
    unsigned fireCallbacks=0,failedFireCallbacks=0;
    explicit AdapterFixture(bool readyForUser=true):policy(readyForUser) {
        CHECK(io::sockets==0);io::posted.clear();io::sent.clear();io::received.clear();io::selectors.clear();io::processes.clear();
        io::failSelector=-1;io::rejectSchedule=false;io::threadValid=true;io::rejectSocket=false;overrideValues.clear();deviceIndex=HBL_FORMAL_FIRE_INDEX;
        radio.completed=[this](FormalRadio::Operation operation,bool ok) {
            const auto action=policy.activeAction();
            CHECK((operation==FormalRadio::Open && action==Policy::Open) ||
                (operation==FormalRadio::Select && (action==Policy::Select || action==Policy::Restore)) ||
                (operation==FormalRadio::Power && action==Policy::Power) ||
                (operation==FormalRadio::Fire && action==Policy::Fire) ||
                (operation==FormalRadio::Close && action==Policy::Close));
            if(operation==FormalRadio::Fire) { ++fireCallbacks;if(!ok) ++failedFireCallbacks; }
            policy.complete(action,ok,now());stepAdapter();
        };
    }
    ~AdapterFixture() { radio.completed=nullptr; }
    void stepAdapter() {
        if(policy.takeCancelDispatch()) formal_cancel_pending(policy,radio);
        const auto command=policy.next(now());bool accepted=true;
        switch(command.action) {
        case Policy::None:return;
        case Policy::Open:accepted=radio.open(policy.channel,policy.wirelessId);break;
        case Policy::Select:case Policy::Restore:accepted=radio.select(command.wave);break;
        case Policy::Power:accepted=radio.sendPower();break;
        case Policy::Fire:accepted=radio.fire(command.deadlineUs);break;
        case Policy::Close:radio.close();break;
        }
        CHECK(accepted);
    }
    void runPosted() {
        for(unsigned i=0;!io::posted.empty();++i) {
            CHECK(i<300);auto callback=io::posted.front();io::posted.pop_front();callback();
        }
    }
    void drain() {
        for(unsigned i=0;i<1000;++i) {
            runPosted();
            if(!io::sent.empty()) {
                auto request=io::sent.front();io::sent.pop_front();io::received.push_back(reply(request));radio.receive();continue;
            }
            if(radio.process.state()==QProcess::Running) {
                if(radio.stage==FormalRadio::ChannelSet) {
                    char response[64];std::snprintf(response,sizeof(response),"Chanspec set to 0x%04x\n",hbl_formal_chanspec(radio.configuredChannel));
                    radio.process.output=QByteArray(response);
                } else if(radio.stage==FormalRadio::GainRead) radio.process.output=QByteArray("txpwrindex for core{0...3}: 10 10 0 0");
                else if(radio.stage==FormalRadio::ReleaseCli) radio.process.output=QByteArray("0x0001");
                radio.process.current=QProcess::NotRunning;radio.processFinished(0,QProcess::NormalExit);continue;
            }
            return;
        }
        CHECK(false);
    }
    void open() {
        CHECK(policy.setOptions(1,1,1,now()));stepAdapter();drain();CHECK(policy.restored());CHECK(radio.ready);
    }
    void arm(unsigned token) {
        CHECK(policy.updateGroup(0,1,40,now()));
        Policy::Group snapshot[HBL_FORMAL_GROUPS];for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) snapshot[i]=policy.groups[i];
        CHECK(policy.flush(token,2000,false,snapshot,now()));stepAdapter();drain();
        Policy::Ack ack;CHECK(policy.popAck(&ack));CHECK(ack.token==token && ack.result==FORMAL_OK);CHECK(policy.shotActive);
    }
    HblMechanicalSync sample(unsigned trial,bool done=false) {
        return HblMechanicalSync{HBL_MECH_MAGIC,1,trial,HBL_MECH_CLOCK|3u|(4u<<8)|(done ? HBL_MECH_DONE:0u),0,4u,1,0,1,0,3};
    }
    void schedule(unsigned trial) {
        auto s=sample(trial);uint64_t at=now();CHECK(policy.mechanicalSample(1,s,at*1000,now()));stepAdapter();
        CHECK(radio.stage==FormalRadio::FireReply);CHECK(radio.dispatch.pending);CHECK(policy.activeAction()==Policy::Fire);
    }
    unsigned cancelFromEndSample(unsigned trial) {
        auto s=sample(trial,true);const uint64_t at=now();CHECK(!policy.mechanicalSample(1,s,at*1000,now()));
        CHECK(policy.takeCancelDispatch());return formal_cancel_pending(policy,radio);
    }
    unsigned cancelFromOptions() {
        CHECK(policy.setOptions(1,1,0,now()));CHECK(policy.takeCancelDispatch());return formal_cancel_pending(policy,radio);
    }
};
static void repeatedCancellation() {
    AdapterFixture f;f.open();f.arm(1);f.schedule(1);
    const unsigned sent=sentCount(40);
    CHECK(f.cancelFromEndSample(1)==Policy::CancelConfirmed);
    CHECK(f.radio.stage==FormalRadio::Finishing);CHECK(f.fireCallbacks==0);
    CHECK(f.cancelFromOptions()==Policy::CancelEmpty);
    CHECK(f.policy.endShot(1,now()));CHECK(f.policy.takeCancelDispatch());CHECK(formal_cancel_pending(f.policy,f.radio)==Policy::CancelEmpty);
    CHECK(f.fireCallbacks==0);f.drain();
    CHECK(f.fireCallbacks==1 && f.failedFireCallbacks==1);CHECK(f.policy.master);CHECK(f.policy.lastError==FORMAL_OK);
    CHECK(f.policy.restored() && f.radio.ready);CHECK(sentCount(40)==sent);
    // 确定取消只绑定上一Fire，不能让下一Fire的真实失败逃过故障关闭。
    CHECK(f.policy.setOptions(1,1,1,now()));f.arm(2);f.schedule(2);io::failSelector=40;f.radio.dispatch.submit();
    CHECK(f.cancelFromEndSample(2)==Policy::CancelFailed);CHECK(f.cancelFromOptions()==Policy::CancelEmpty);
    f.drain();CHECK(!f.policy.master);CHECK(f.policy.lastError==FORMAL_RADIO_ERROR);CHECK(!f.radio.held);
}
static void submittedAndEmpty() {
    for(unsigned reject=0;reject<2;++reject) {
        AdapterFixture f;f.open();f.arm(1);f.schedule(1);f.radio.dispatch.submit();
        CHECK(f.cancelFromEndSample(1)==Policy::CancelSubmitted);
        CHECK(f.cancelFromOptions()==Policy::CancelSubmitted);CHECK(f.fireCallbacks==0);
        if(reject) overrideValues[40]=0;
        f.drain();CHECK(sentCount(40)==1);CHECK(f.fireCallbacks==1);CHECK(f.policy.master==!reject);
        CHECK(f.policy.lastError==(reject ? FORMAL_RADIO_ERROR:FORMAL_OK));
    }
    AdapterFixture timeout;timeout.open();timeout.arm(1);timeout.schedule(1);
    timeout.radio.timedOut();CHECK(timeout.radio.stage==FormalRadio::Finishing);
    CHECK(timeout.cancelFromOptions()==Policy::CancelEmpty);timeout.drain();
    CHECK(!timeout.policy.master);CHECK(timeout.policy.lastError==FORMAL_RADIO_ERROR);CHECK(sentCount(40)==0);
}
static void oldPowerMustNotRevive() {
    for(unsigned boundary=0;boundary<2;++boundary) {
        AdapterFixture f;f.open();CHECK(f.policy.updateGroup(0,1,40,now()));f.stepAdapter();
        CHECK(f.policy.activeAction()==Policy::Select);CHECK(f.radio.stage==FormalRadio::Preparing);
        const unsigned before=sentCount(48);
        CHECK(f.policy.setOptions(boundary ? 1:0,boundary ? 0:1,1,now()));
        CHECK(f.policy.setOptions(1,1,1,now()));f.stepAdapter();f.drain();
        CHECK(sentCount(48)==before);CHECK(f.policy.restored());CHECK(f.policy.master);
        CHECK(f.policy.updateGroup(0,1,50,now()));f.stepAdapter();f.drain();CHECK(sentCount(48)==before+1);
    }
    AdapterFixture flush;flush.open();
    Policy::Group before[HBL_FORMAL_GROUPS];for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) { before[i].active=1;before[i].tenths=40; }
    CHECK(flush.policy.flush(1,2000,false,before,now()));flush.stepAdapter();CHECK(flush.policy.activeAction()==Policy::Select);
    CHECK(flush.policy.cancel(1,now()));Policy::Ack ack;CHECK(flush.policy.popAck(&ack));CHECK(ack.token==1 && ack.result==FORMAL_CANCELLED);
    for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) before[i].tenths=80;
    CHECK(flush.policy.flush(2,2000,false,before,now()));flush.stepAdapter();flush.drain();
    CHECK(flush.policy.popAck(&ack));CHECK(ack.token==2 && ack.result==FORMAL_OK);
    CHECK(sentCount(48)==HBL_FORMAL_GROUPS);CHECK(flush.policy.restored());CHECK(sentCount(40)==0);
}
static void stopLock() {
    AdapterFixture f;f.open();f.arm(1);f.schedule(1);f.policy.requestStop(now());f.stepAdapter();
    CHECK(f.policy.stopLocked);CHECK(!f.policy.master);CHECK(!f.policy.stoppedSafely(f.radio.held,f.radio.busy,f.radio.ready));
    f.policy.newSession(now());CHECK(!f.policy.setOptions(1,1,1,now()));f.stepAdapter();f.drain();
    CHECK(f.policy.stoppedSafely(f.radio.held,f.radio.busy,f.radio.ready));CHECK(sentCount(40)==0);
    CHECK(!f.policy.setOptions(1,1,1,now()));CHECK(f.policy.stopLocked);
    AdapterFixture failed;failed.open();overrideValues[27]=0;failed.policy.requestStop(now());failed.stepAdapter();failed.drain();
    CHECK(failed.policy.stopFailed);CHECK(!failed.policy.stoppedSafely(failed.radio.held,failed.radio.busy,failed.radio.ready));
    failed.policy.newSession(now());CHECK(!failed.policy.setOptions(1,1,1,now()));CHECK(failed.policy.stopFailed);
}
static void installationGate() {
    {
        AdapterFixture f(false);
        CHECK(!f.policy.installationReady);CHECK(!f.policy.canConfirmInstallationReady());
        const uint64_t oldRequest=now();CHECK(!f.policy.setOptions(1,1,1,now(),oldRequest));
        CHECK(f.policy.updateGroup(0,1,80,now()));f.stepAdapter();CHECK(io::sent.empty());CHECK(!f.policy.master);
        CHECK(f.policy.setOptions(0,1,1,now()));f.policy.newSession(now());
        CHECK(!f.policy.installationReady);CHECK(!f.policy.setOptions(1,1,1,now()));
        io::clockUs+=2000;CHECK(f.policy.unlockInstallation(now()));CHECK(f.policy.canConfirmInstallationReady());
        f.stepAdapter();CHECK(io::sent.empty());CHECK(!f.policy.master);
        // 在闸门打开前发出的包即使迟到，也不能转换成新启用意图。
        CHECK(!f.policy.setOptions(1,1,1,now(),oldRequest));CHECK(!f.policy.setOptions(1,1,1,now()));
        io::clockUs+=2000;CHECK(f.policy.setOptions(1,1,1,now()));f.stepAdapter();f.drain();
        CHECK(f.policy.master && f.policy.restored());CHECK(sentCount(48)==0 && sentCount(40)==0);
        f.policy.newSession(now());CHECK(f.policy.installationReady);CHECK(!f.policy.master);
        f.stepAdapter();f.drain();
    }
    {
        AdapterFixture f(false);f.policy.requestStop(now());CHECK(f.policy.stopLocked);
        CHECK(!f.policy.unlockInstallation(now()));CHECK(!f.policy.canConfirmInstallationReady());
        f.policy.newSession(now());CHECK(!f.policy.unlockInstallation(now()));
        CHECK(!f.policy.setOptions(1,1,1,now()));CHECK(!f.policy.canConfirmInstallationReady());f.stepAdapter();CHECK(io::sent.empty());
    }
    {
        AdapterFixture f(false);CHECK(f.policy.unlockInstallation(now()));CHECK(f.policy.canConfirmInstallationReady());
        f.policy.requestStop(now());CHECK(!f.policy.canConfirmInstallationReady());CHECK(!f.policy.unlockInstallation(now()));
    }
}
static void expandedControls() {
    {
        AdapterFixture f;f.open();f.arm(1);f.schedule(1);
        CHECK(f.policy.setWireless(32,0,now()));f.stepAdapter();f.drain();
        CHECK(sentCount(40)==0 && f.failedFireCallbacks==1);
        CHECK(f.policy.master && f.policy.restored() && f.radio.ready);
        CHECK(f.radio.configuredChannel==32 && f.radio.configuredId==0 && deviceChannel==32 && deviceId==0);
        CHECK(!f.policy.shotActive && !f.radio.dispatch.pending);
        const auto old=f.sample(1);const uint64_t at=now();
        CHECK(!f.policy.mechanicalSample(1,old,at*1000,now()));f.stepAdapter();f.drain();CHECK(sentCount(40)==0);
    }
    {
        AdapterFixture f;f.open();CHECK(f.policy.updateGroup(15,1,80,now()));f.stepAdapter();
        CHECK(f.policy.activeAction()==Policy::Select);
        CHECK(f.policy.setWireless(1,99,now()));f.stepAdapter();f.drain();
        CHECK(sentCount(48)==0 && sentCount(40)==0 && f.policy.restored());
        CHECK(deviceChannel==1 && deviceId==99);
        CHECK(f.policy.updateLamp(15,1,now()));f.stepAdapter();f.drain();
        CHECK(sentCount(48)==1 && sentCount(40)==0 && f.policy.restored());
        CHECK(std::find(io::selectors.begin(),io::selectors.end(),512+HBL_FORMAL_LAMP_BASE+31)!=io::selectors.end());
    }
    {
        AdapterFixture f;f.open();CHECK(!f.policy.test(now()));
        CHECK(f.policy.updateGroup(15,1,40,now()));f.stepAdapter();f.drain();
        const unsigned before=sentCount(48);CHECK(f.policy.test(now()));f.stepAdapter();f.drain();
        CHECK(sentCount(48)==before+HBL_FORMAL_GROUPS && sentCount(40)==0 && f.radio.dispatch.pending);
        // 全部十六组已完成准备，才允许提交唯一一次广播。
        f.radio.dispatch.submit();f.drain();CHECK(sentCount(40)==1 && f.policy.restored());
        CHECK(f.policy.updateGroup(15,0,40,now()));f.stepAdapter();f.drain();
        CHECK(!f.policy.test(now()) && sentCount(40)==1);
    }
}
int main() {
    try { repeatedCancellation();submittedAndEmpty();oldPowerMustNotRevive();stopLock();installationGate();expandedControls(); }
    catch(const std::exception &error) { std::fprintf(stderr,"%s\n",error.what());return 1; }
    std::printf("formal-policy-adapter-checks=%u hardware-requests=0\n",checks);return 0;
}
