#include "formal_radio_fake_platform.h"
#define HBL_FORMAL_RADIO_TEST_PLATFORM "formal_radio_fake_platform.h"
#define private public
#include "../native/formal_radio.h"
#undef private
namespace test=formal_test;
static unsigned checks=0,deviceIndex=HBL_FORMAL_FIRE_INDEX,deviceChannel=5,deviceId=5;
static std::map<unsigned,uint32_t> overrides;
static bool badGain=false;
static const char *channelOverride=nullptr;
static void check(bool result,const char *why) { if (!result) throw std::runtime_error(why); ++checks; }
static void posted() {
    unsigned count=0;
    while(!test::posted.empty()) {
        if (++count>100) throw std::runtime_error("callback loop");
        auto callback=test::posted.front(); test::posted.pop_front(); callback();
    }
}
static std::vector<uint8_t> response(const std::vector<uint8_t> &request) {
    uint8_t out[128]={},word[8]={},nested[64]={};
    const bool family=rf_le16(request.data()+4)==16;
    size_t used=rf_nl_begin(out,sizeof(out),family ? 16 : 35,rf_le32(request.data()+8),99,family ? 1 : 103);
    if (family) {
        rf_put16(word,35); rf_nl_add(out,sizeof(out),&used,1,word,2);
        rf_nl_add(out,sizeof(out),&used,2,"nl80211",8);
    } else {
        const unsigned selector=rf_le32(request.data()+68);
        if (selector==14) deviceIndex=HBL_FORMAL_FIRE_INDEX;
        if (selector>=512 && selector<512+HBL_FORMAL_CONTROL_WAVES) deviceIndex=selector-512;
        if(selector>=HBL_FORMAL_CONFIG_BASE && selector<HBL_FORMAL_CONFIG_BASE+HBL_FORMAL_CONFIG_COUNT) {
            deviceChannel=(selector-HBL_FORMAL_CONFIG_BASE)/100+1;deviceId=(selector-HBL_FORMAL_CONFIG_BASE)%100;
        }
        uint32_t hash=0;
        if(selector==15 || selector==16) hbl_formal_wave_hash(&hash,deviceIndex,deviceChannel,deviceId,hbl_formal_lut);
        uint32_t value=1;
        if(selector==19) value=deviceChannel;
        if(selector==20) value=deviceId;
        if (selector==0) value=0x5854;
        if (selector==15) value=hash&0xffff;
        if (selector==16) value=hash>>16;
        if (selector==18) value=deviceIndex;
        if (overrides.count(selector)) value=overrides[selector];
        rf_put16(nested,6); rf_put16(nested+2,1); rf_put16(nested+4,4);
        rf_put16(nested+8,8); rf_put16(nested+10,2); rf_put32(nested+12,value);
        rf_nl_add(out,sizeof(out),&used,197,nested,16);
    }
    return std::vector<uint8_t>(out,out+used);
}
static void oneReply(FormalRadio &radio) {
    check(!test::sent.empty(),"missing driver request");
    auto request=test::sent.front(); test::sent.pop_front();
    test::received.push_back(response(request)); radio.receive();
}
static void finishProcess(FormalRadio &radio) {
    if (radio.stage==FormalRadio::ChannelSet) {
        char response[64];std::snprintf(response,sizeof(response),"Chanspec set to 0x%04x\n",hbl_formal_chanspec(radio.configuredChannel));
        radio.process.output=QByteArray(channelOverride ? channelOverride : response);
    } else if (radio.stage==FormalRadio::GainRead)
        radio.process.output=QByteArray(badGain ? "txpwrindex for core{0...3}: 10 20 0 0" : "txpwrindex for core{0...3}: 10 10 0 0");
    else if (radio.stage==FormalRadio::ReleaseCli) radio.process.output=QByteArray("0x0001");
    radio.process.current=QProcess::NotRunning;
    radio.processFinished(0,QProcess::NormalExit);
}
static void pump(FormalRadio &radio) {
    for (unsigned i=0;i<100;++i) {
        posted();
        if (!test::sent.empty()) { oneReply(radio); continue; }
        if (radio.process.state()==QProcess::Running) { finishProcess(radio); continue; }
        return;
    }
    throw std::runtime_error("state loop");
}
static unsigned count(unsigned selector) { return unsigned(std::count(test::selectors.begin(),test::selectors.end(),selector)); }
struct Fixture {
    FormalRadio radio;
    std::vector<std::pair<FormalRadio::Operation,bool>> events;
    Fixture() {
        check(!test::sockets,"prior fd leak"); test::selectors.clear();test::processes.clear();
        test::sent.clear();test::received.clear();overrides.clear();
        test::failSelector=-1;test::rejectSchedule=false;badGain=false;channelOverride=nullptr;
        radio.completed=[this](FormalRadio::Operation operation,bool ok) { events.push_back({operation,ok}); };
    }
    void open() {
        check(radio.open(),"open refused"); check(events.empty(),"callback ran synchronously");pump(radio);
        check(radio.ready && radio.held && !radio.busy && radio.selectedIndex==HBL_FORMAL_FIRE_INDEX,"open did not validate fire");
        check(events==std::vector<std::pair<FormalRadio::Operation,bool>>{{FormalRadio::Open,true}},"open completion wrong");
    }
    ~Fixture() { radio.close();pump(radio); }
};
int main() {
    try {
        {
            Fixture f;f.open();
            const std::vector<unsigned> handshake={0,27,26,hbl_formal_config_selector(5,5),19,20,14,15,16,17,18};
            check(test::selectors==handshake,"wrong normal handshake");
            check(test::processes==std::vector<std::vector<std::string>>{{"chanspec","2/20"},{"phy_txpwrindex","10","10"},{"phy_txpwrindex"}},"gain commands not fixed");
            const auto attempts=test::attempts;
            check(!f.radio.sendPower() && !f.radio.select(HBL_FORMAL_WAVES) && !f.radio.open(),"wrong type or duplicate open accepted");
            check(test::attempts==attempts,"invalid input performed IO");
            for (unsigned index=0;index<HBL_FORMAL_WAVES;++index) {
                check(f.radio.select(index),"valid selection rejected");
                check(!f.radio.fire() && !f.radio.sendPower(),"sending before selection verified");
                pump(f.radio);check(f.radio.ready && f.radio.selectedIndex==index,"selection state mismatch");
            }
            check(f.radio.select(81),"off wave refused");pump(f.radio);
            const auto before=count(14);
            check(f.radio.sendPower(),"power refused");pump(f.radio);
            check(count(48)==1 && count(40)==0 && count(14)==before && f.radio.selectedIndex==81,"power emitted sync or secretly restored buffer");
            check(f.radio.select(HBL_FORMAL_FIRE_INDEX),"restore refused");pump(f.radio);
            const auto fired=count(40);
            check(f.radio.fire(test::clockUs+12345),"fire refused");
            check(f.radio.dispatch.pending && f.radio.dispatch.target==test::clockUs+12345 && count(40)==fired,"deadline sent immediately");
            check(!f.radio.select(0) && !f.radio.fire() && !f.radio.sendPower(),"pending fire overwritten");
            check(f.radio.cancelPending()==MechanicalDirectDispatch::Cancelled,"cancellation not guaranteed");
            posted();check(count(40)==fired && f.radio.ready && !f.radio.busy,"cancel sent or disabled verified selection");
            check(f.radio.fire(),"fire after cancellation refused");
            f.radio.dispatch.submit();
            check(f.radio.cancelPending()==MechanicalDirectDispatch::Submitted,"committed dispatch falsely cancelled");
            check(f.radio.busy && !f.radio.ready,"commit became ready before reply");
            pump(f.radio);check(count(40)==fired+1 && f.radio.ready,"fire missing or repeated");
            check(f.radio.cancelPending()==MechanicalDirectDispatch::Empty,"old completion retained");
        }
        for (unsigned selector : {15u,16u,17u,18u}) {
            Fixture f;f.open();overrides[selector]=0xffff;
            check(f.radio.select(0),"mismatch setup refused");pump(f.radio);
            check(!f.radio.ready && !f.radio.held && !f.radio.busy,"mismatch did not fail closed");
            check(count(27)==2 && count(40)==0 && count(48)==0,"mismatch retried or failed to release");
            check(f.events[f.events.size()-2]==std::make_pair(FormalRadio::Select,false),"mismatch not surfaced");
        }
        {
            Fixture f;overrides[0]=0x5851;
            check(f.radio.open(),"marker setup refused");pump(f.radio);
            check(!f.radio.held && !f.radio.ready && count(27)==0 && test::processes.empty(),"wrong marker changed RF state");
        }
        {
            Fixture f;badGain=true;check(f.radio.open(),"gain setup refused");pump(f.radio);
            check(!f.radio.ready && count(26)==0 && count(14)==0,"gain mismatch held or prepared");
        }
        for (const char *reply : {"", "Chanspec set to 0x1003", "Chanspec set to garbage", "Chanspec set to 0x1002 extra", "unexpected success"}) {
            Fixture f;channelOverride=reply;check(f.radio.open(),"channel reply test rejected");pump(f.radio);
            check(f.radio.ready==!reply[0],"invalid channel success reply accepted");
            if(reply[0]) check(count(26)==0 && count(14)==0,"bad channel reply reached prepare");
        }
        for(unsigned channel=1;channel<=32;++channel) {
            Fixture f;check(f.radio.open(channel,0),"dynamic channel reply setup");pump(f.radio);
            check(f.radio.ready && f.radio.configuredChannel==channel,"real formatted channel success was rejected");
        }
        {
            Fixture f;f.open();check(f.radio.select(0),"power setup refused");pump(f.radio);
            test::failSelector=48;check(f.radio.sendPower(),"power failure not accepted");pump(f.radio);
            check(count(48)==1 && count(40)==0 && count(27)==2 && !f.radio.held,"power submission failure retried or did not release");
        }
        {
            Fixture f;f.open();test::rejectSchedule=true;check(f.radio.fire(),"deadline failure not accepted");pump(f.radio);
            check(count(40)==0 && count(27)==2 && !f.radio.ready,"schedule failure emitted or retained ready");
        }
        {
            Fixture f;f.open();check(f.radio.fire(test::clockUs+50000),"close setup refused");
            f.radio.close();pump(f.radio);
            check(count(40)==0 && count(27)==2 && !f.radio.held && !f.radio.busy,"close did not cancel pending dispatch");
        }
        {
            Fixture f;f.open();check(f.radio.fire(),"committed close setup refused");
            f.radio.dispatch.submit();f.radio.close();
            check(count(27)==1 && f.radio.busy,"close released before committed reply");
            pump(f.radio);check(count(40)==1 && count(27)==2 && !f.radio.held,"committed close repeated fire or failed release");
        }
        {
            Fixture f;f.open();overrides[27]=9;f.radio.close();pump(f.radio);
            check(f.radio.held && !f.radio.ready && !f.radio.busy && count(27)==2,"release rejection falsely succeeded");
            f.radio.close();pump(f.radio);check(count(27)==2,"release rejection caused retry loop");
            check(!f.radio.open(),"uncertain ownership reopened");
        }
        {
            Fixture f;f.open();f.radio.sequence=UINT32_MAX;
            check(f.radio.select(0),"exhaustion not accepted");pump(f.radio);
            check(!f.radio.held && !f.radio.ready && test::processes.back()==std::vector<std::string>{"phyreg","27","b"},"sequence exhaustion did not use bounded release");
        }
        {
            Fixture f;check(f.radio.open(),"early close setup refused");f.radio.close();pump(f.radio);
            check(test::selectors.empty() && !f.radio.held && !f.radio.busy,"close before open still configured RF");
        }
        {
            Fixture f;f.open();check(f.radio.fire(),"timeout setup refused");f.radio.dispatch.submit();
            f.radio.finishDispatch(f.radio.dispatch.take());test::sent.clear();f.radio.timedOut();pump(f.radio);
            check(count(40)==1 && count(27)==2 && !f.radio.ready,"fire timeout retried or retained readiness");
        }
        {
            Fixture f;f.open();check(f.radio.select(1),"malformed setup refused");
            auto bytes=response(test::sent.front());test::sent.pop_front();bytes[20]=3;
            test::received.push_back(bytes);f.radio.receive();pump(f.radio);
            check(!f.radio.held && !f.radio.ready && count(27)==2,"malformed reply did not release");
        }
        posted();check(!test::sockets,"socket leak");
        std::cout<<"formal-radio-state-checks="<<checks<<" hardware-requests=0\n";return 0;
    } catch(const std::exception &error) { std::cerr<<error.what()<<"\n";return 1; }
}
