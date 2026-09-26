#ifdef NDEBUG
#undef NDEBUG
#endif
#include "../native/formal_policy.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
static unsigned checks=0;
#define CHECK(value) do { ++checks;if(!(value)) { std::fprintf(stderr,"line %u: %s\n",__LINE__,#value);std::exit(1); } } while(0)
using Policy=FormalPolicy;
struct Fixture {
    Policy p;uint64_t now=1000000;
    std::vector<Policy::Command> log;
    uint64_t step() { return ++now; }
    Policy::Command next() { auto c=p.next(step());if(c.action!=Policy::None) log.push_back(c);return c; }
    void finish(Policy::Action a,bool ok=true) { p.complete(a,ok,step()); }
    void drain() {
        for(unsigned i=0;i<100;++i) { auto c=next();if(c.action==Policy::None) return;finish(c.action); }
        CHECK(false);
    }
    void options(bool m,bool p=true,bool s=true) { CHECK(this->p.setOptions(m,p,s,step())); }
    void update(unsigned g,unsigned active,unsigned t) { CHECK(p.updateGroup(g,active,t,step())); }
    bool flush(unsigned token=1,unsigned exposure=2000,bool es=false) {
        Policy::Group snapshot[HBL_FORMAL_GROUPS];for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) snapshot[i]=p.groups[i];
        return p.flush(token,exposure,es,snapshot,step());
    }
    Policy::Ack ack(unsigned token,unsigned result) {
        Policy::Ack a={};CHECK(p.popAck(&a));CHECK(a.token==token);CHECK(a.result==result);return a;
    }
    void noAck() { Policy::Ack a={};CHECK(!p.popAck(&a)); }
    unsigned count(Policy::Action a) { unsigned n=0;for(auto c:log) n+=c.action==a;return n; }
    HblMechanicalSync mech(unsigned trial=1) {
        return HblMechanicalSync{HBL_MECH_MAGIC,1,trial,HBL_MECH_CLOCK|2u|(2u<<8),0,HBL_MECH_B,1,0,1,0,3};
    }
    HblFarmSync es(unsigned shot=1,unsigned exposure=250000,unsigned source=0) {
        return HblFarmSync{HBL_SYNC_MAGIC,3,shot,7u|(source<<8),0,HBL_SYNC_STATUS_BIT,1,0,1,exposure,0};
    }
    void armed(bool electronic=false) { update(0,1,40);options(true);drain();CHECK(flush(1,2000,electronic));drain();ack(1,FORMAL_OK);CHECK(p.shotActive); }
};
static void schema() {
    FormalPacket p;formal_packet_init(&p,FORMAL_HELLO,1,0,1000);CHECK(sizeof(p)==FORMAL_PACKET_BYTES);CHECK(formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES-1));p.sequence=1;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    formal_packet_init(&p,FORMAL_OPTIONS,1,1,1000);CHECK(formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    for(unsigned slot=0;slot<FV_COUNT;++slot) {
        FormalPacket bad=p;bad.values[slot]=2;
        CHECK(!formal_packet_valid(&bad,FORMAL_PACKET_BYTES));
    }
    formal_packet_init(&p,FORMAL_GROUP,1,2,1000);p.values[FV_GROUP]=4;p.values[FV_ACTIVE]=1;p.values[FV_TENTHS]=80;
    CHECK(formal_packet_valid(&p,FORMAL_PACKET_BYTES));p.values[FV_GROUP]=HBL_FORMAL_GROUPS;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));p.values[FV_GROUP]=4;
    p.values[FV_TENTHS]=81;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));p.values[FV_TENTHS]=80;p.text[3]='x';CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    formal_packet_init(&p,FORMAL_FLUSH,1,3,1000);p.values[FV_TOKEN]=1;p.values[FV_EXPOSURE_LO]=2000;
    CHECK(formal_packet_valid(&p,FORMAL_PACKET_BYTES));p.values[FV_GROUP_E_TENTHS]=81;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    p.values[FV_GROUP_E_TENTHS]=80;p.values[FV_ELECTRONIC]=2;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    formal_packet_init(&p,FORMAL_TEST,1,4,1000);CHECK(formal_packet_valid(&p,FORMAL_PACKET_BYTES));p.values[FV_TOKEN]=1;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    formal_packet_init(&p,FORMAL_FLUSH_ACK,1,4,1000);CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));p.values[FV_ACK_TOKEN]=1;CHECK(formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    p.values[FV_COUNT-1]=1;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    formal_packet_init(&p,FORMAL_STATUS,1,5,1000);p.values[FV_PENDING]=HBL_FORMAL_GROUP_MASK+1;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    p.values[FV_PENDING]=0;p.values[FV_GROUP_C_ACTIVE]=2;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
    p.values[FV_GROUP_C_ACTIVE]=0;p.values[FV_TOKEN]=1;CHECK(!formal_packet_valid(&p,FORMAL_PACKET_BYTES));
}
static void gates() {
    for(unsigned bits=0;bits<8;++bits) {
        Fixture f;bool m=bits&1,p=bits&2,s=bits&4;
        f.options(m,p,s);f.drain();CHECK(f.count(Policy::Power)==0);CHECK(f.count(Policy::Fire)==0);
        f.update(0,1,50);f.drain();CHECK(f.count(Policy::Power)==unsigned(m&&p));CHECK(f.count(Policy::Fire)==0);
        CHECK(f.flush());f.drain();f.ack(1,m&&s&&!p ? FORMAL_GROUPS_UNSENT : FORMAL_OK);CHECK(f.count(Policy::Power)==unsigned(m&&p)*(HBL_FORMAL_GROUPS+1));
        auto sample=f.mech();const uint64_t at=f.step();bool accepted=f.p.mechanicalSample(1,sample,at*1000,f.step());
        CHECK(accepted==bool(m&&s&&p));f.drain();CHECK(f.count(Policy::Fire)==unsigned(m&&s&&p));
    }
    Fixture f;f.update(0,1,60);f.options(true);f.drain();CHECK(f.count(Policy::Power)==0);
    f.options(true,false);f.update(0,1,70);f.options(true,true);f.drain();CHECK(f.count(Policy::Power)==0);
    f.options(true,true,false);f.update(0,1,80);f.drain();CHECK(f.count(Policy::Power)==1);CHECK(f.count(Policy::Fire)==0);
    CHECK(!f.p.updateGroup(HBL_FORMAL_GROUPS,1,40,f.step()));CHECK(!f.p.updateGroup(0,1,81,f.step()));CHECK(!f.p.setOptions(2,1,1,f.step()));
}
static void bufferAndQueue() {
    Fixture f;f.options(true);f.drain();f.update(0,1,40);
    auto select=f.next();CHECK(select.action==Policy::Select);CHECK(select.wave==40);
    f.update(0,1,41);f.update(0,1,42);f.finish(Policy::Select);
    CHECK(f.next().action==Policy::Power);f.finish(Policy::Power);CHECK(!f.p.restored());
    CHECK(f.next().action==Policy::Restore);f.finish(Policy::Restore);CHECK(f.p.restored());
    select=f.next();CHECK(select.action==Policy::Select);CHECK(select.wave==38);f.finish(Policy::Select);f.drain();CHECK(f.count(Policy::Power)==2);

    Fixture q;q.options(true);q.drain();q.update(0,1,40);auto old=q.next();CHECK(old.action==Policy::Select);
    CHECK(q.flush());q.update(0,1,80);q.finish(Policy::Select);q.drain();q.ack(1,FORMAL_OK);
    CHECK(q.count(Policy::Power)==HBL_FORMAL_GROUPS+1);CHECK(q.p.dirty==1);CHECK(q.p.restored());
    CHECK(q.p.endShot(1,q.step()));q.drain();CHECK(q.count(Policy::Power)==HBL_FORMAL_GROUPS+2);
    unsigned zeroWaves=0;for(auto c:q.log) if(c.action==Policy::Select && c.wave==0) ++zeroWaves;CHECK(zeroWaves==1);
    // 每个已发送功率之后必须先恢复同步波形，之后才可能下一功率或同步。
    bool awaitingRestore=false;
    for(auto c:q.log) {
        if(c.action==Policy::Power) { CHECK(!awaitingRestore);awaitingRestore=true; }
        if(c.action==Policy::Restore) { CHECK(awaitingRestore);CHECK(c.wave==HBL_FORMAL_FIRE_INDEX);awaitingRestore=false; }
        if(c.action==Policy::Fire) CHECK(!awaitingRestore);
    }
    CHECK(!awaitingRestore);
}
static void flushCompletion() {
    Fixture f;f.options(true);f.drain();CHECK(f.flush());f.noAck();
    for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) {
        CHECK(f.next().action==Policy::Select);f.finish(Policy::Select);
        CHECK(f.next().action==Policy::Power);f.finish(Policy::Power);f.noAck();
        CHECK(f.next().action==Policy::Restore);f.noAck();f.finish(Policy::Restore);
        if(i<HBL_FORMAL_GROUPS-1) f.noAck();
    }
    f.ack(1,FORMAL_OK);CHECK(f.p.restored());CHECK(f.p.shotActive);CHECK(f.count(Policy::Fire)==0);
    CHECK(!f.flush(2));f.ack(2,FORMAL_REJECTED);CHECK(f.p.token==1);
    CHECK(f.p.endShot(1,f.step()));CHECK(!f.flush(1));f.ack(1,FORMAL_REJECTED);
    CHECK(f.flush(2));f.drain();f.ack(2,FORMAL_OK);
    f.p.newSession(f.step());f.options(true);f.drain();CHECK(f.flush(1));f.drain();f.ack(1,FORMAL_OK);
}
static void cancellationAndFaults() {
    for(auto failure:{Policy::Open,Policy::Select,Policy::Power,Policy::Restore}) {
        Fixture f;f.options(true);CHECK(f.flush());
        for(unsigned i=0;i<30;++i) {
            auto c=f.next();CHECK(c.action!=Policy::None);
            if(c.action==failure) { f.finish(c.action,false);break; }
            f.finish(c.action);
        }
        f.ack(1,FORMAL_RADIO_ERROR);CHECK(!f.p.master);f.drain();CHECK(!f.p.ready);CHECK(!f.p.held);CHECK(f.count(Policy::Fire)==0);f.noAck();
    }
    Fixture f;f.options(true);f.drain();CHECK(f.flush());CHECK(f.next().action==Policy::Select);
    CHECK(f.p.cancel(1,f.step()));f.ack(1,FORMAL_CANCELLED);f.finish(Policy::Select);f.drain();CHECK(f.count(Policy::Power)==0);CHECK(f.p.restored());
    CHECK(f.flush(2));CHECK(f.next().action==Policy::Select);f.finish(Policy::Select);CHECK(f.next().action==Policy::Power);
    f.now+=uint64_t(FORMAL_FLUSH_TIMEOUT_MS)*1000;f.p.tick(f.step());f.ack(2,FORMAL_TIMEOUT);CHECK(!f.p.master);
    f.finish(Policy::Power);f.drain();CHECK(f.count(Policy::Restore)==2);CHECK(f.count(Policy::Power)==1);f.noAck();

    Fixture p;p.options(true);p.drain();p.update(0,1,80);CHECK(p.next().action==Policy::Select);
    p.options(true,false);p.finish(Policy::Select);p.drain();CHECK(p.count(Policy::Power)==0);CHECK(p.p.restored());
    Fixture power;power.options(true);power.drain();CHECK(power.flush());power.options(true,false);power.ack(1,FORMAL_CANCELLED);power.drain();CHECK(power.count(Policy::Power)==0);
    Fixture off;off.armed();off.options(false);CHECK(!off.p.shotActive);off.drain();CHECK(off.count(Policy::Close)==1);
    Fixture lost;lost.armed();lost.p.disconnect(lost.step());lost.drain();CHECK(!lost.p.master);CHECK(!lost.p.held);
    Fixture rollback;rollback.options(true);rollback.drain();rollback.p.tick(rollback.now-1);CHECK(!rollback.p.master);
}
static void mechanicalTiming() {
    const unsigned exposures[]={8000,6250,5000,4000,3125,2500,2000,1563,1250,1000,800,625,500};
    const unsigned delays[]={5000,5000,5000,5000,5570,5980,6300,6560,6750,6900,6900,6900,6900};
    for(unsigned i=0;i<13;++i) { unsigned delay=0;CHECK(formal_mechanical_delay(exposures[i],&delay));CHECK(delay==delays[i]); }
    unsigned delay=0;CHECK(formal_mechanical_delay(1000000,&delay));CHECK(delay==5000);CHECK(!formal_mechanical_delay(777,&delay));
    Fixture f;f.armed();auto sample=f.mech();sample.mode=1; // 原厂GMS mode1仍是机械，不当电子开关。
    const uint64_t at=f.step();CHECK(f.p.mechanicalSample(1,sample,at*1000,f.step()));
    CHECK(!f.p.mechanicalSample(1,sample,at*1000,f.step()));auto command=f.next();CHECK(command.action==Policy::Fire);CHECK(command.deadlineUs==at+6300);
    f.finish(Policy::Fire);CHECK(!f.p.mechanicalSample(1,sample,f.step()*1000,f.step()));f.drain();CHECK(f.count(Policy::Fire)==1);

    Fixture cancel;cancel.armed();sample=cancel.mech();uint64_t t=cancel.step();CHECK(cancel.p.mechanicalSample(1,sample,t*1000,cancel.step()));
    CHECK(cancel.next().action==Policy::Fire);sample.clear_flags|=HBL_MECH_DONE;
    t=cancel.step();CHECK(!cancel.p.mechanicalSample(1,sample,t*1000,cancel.step()));CHECK(cancel.p.takeCancelDispatch());
    cancel.p.dispatchCancellationResult(Policy::CancelConfirmed);cancel.finish(Policy::Fire,false);CHECK(cancel.p.master);cancel.drain();CHECK(cancel.count(Policy::Fire)==1);
    Fixture submitted;submitted.armed();sample=submitted.mech();t=submitted.step();CHECK(submitted.p.mechanicalSample(1,sample,t*1000,submitted.step()));
    CHECK(submitted.next().action==Policy::Fire);CHECK(submitted.p.cancel(1,submitted.step()));CHECK(submitted.p.takeCancelDispatch());
    submitted.p.dispatchCancellationResult(Policy::CancelSubmitted);submitted.finish(Policy::Fire,false);CHECK(!submitted.p.master);
    Fixture before;before.armed();sample=before.mech();CHECK(!before.p.mechanicalSample(1,sample,UINT64_C(1000),before.step()));
    sample.timer_control=0;CHECK(!before.p.mechanicalSample(1,sample,before.now*1000,before.step()));CHECK(before.count(Policy::Fire)==0);
    Fixture epoch;epoch.armed();sample=epoch.mech();t=epoch.step();CHECK(epoch.p.mechanicalSample(1,sample,t*1000,epoch.step()));
    sample.trial=2;t=epoch.step();CHECK(!epoch.p.mechanicalSample(2,sample,t*1000,epoch.step()));CHECK(!epoch.p.master);epoch.drain();CHECK(epoch.count(Policy::Fire)==0);
    Fixture newer;newer.armed();sample=newer.mech();t=newer.step();CHECK(newer.p.mechanicalSample(1,sample,t*1000,newer.step()));
    sample.trial=2;t=newer.step();CHECK(!newer.p.mechanicalSample(1,sample,t*1000,newer.step()));newer.drain();CHECK(newer.count(Policy::Fire)==0);
    // 新的一轮快门不得借用上一trial的迟到消息，即使Linux到达时间较新。
    Fixture delayed;delayed.armed();sample=delayed.mech();t=delayed.step();CHECK(delayed.p.mechanicalSample(1,sample,t*1000,delayed.step()));
    delayed.drain();CHECK(delayed.p.endShot(1,delayed.step()));CHECK(delayed.flush(2));delayed.drain();delayed.ack(2,FORMAL_OK);
    t=delayed.step();CHECK(!delayed.p.mechanicalSample(1,sample,t*1000,delayed.step()));
    sample.trial=2;t=delayed.step();CHECK(delayed.p.mechanicalSample(1,sample,t*1000,delayed.step()));delayed.drain();CHECK(delayed.count(Policy::Fire)==2);
    // flush等待期间收到的任何旧节点也不能在ACK后重复取得资格。
    Fixture during;during.update(0,1,40);during.options(true);during.drain();CHECK(during.flush());sample=during.mech(9);t=during.step();
    CHECK(!during.p.mechanicalSample(1,sample,t*1000,during.step()));during.drain();during.ack(1,FORMAL_OK);
    t=during.step();CHECK(!during.p.mechanicalSample(1,sample,t*1000,during.step()));sample.trial=10;t=during.step();
    CHECK(during.p.mechanicalSample(1,sample,t*1000,during.step()));during.drain();CHECK(during.count(Policy::Fire)==1);
    Fixture order;order.armed();sample=order.mech();sample.clear_flags=HBL_MECH_CLOCK|1|(1<<8);sample.sync_status=HBL_MECH_A;
    t=order.step();CHECK(!order.p.mechanicalSample(1,sample,t*1000,order.step()));sample=order.mech();
    CHECK(!order.p.mechanicalSample(1,sample,(t-1)*1000,order.step()));t=order.step();CHECK(order.p.mechanicalSample(1,sample,t*1000,order.step()));
}
static void electronicTiming() {
    Fixture f;f.armed(true);auto sample=f.es();uint64_t at=f.step();CHECK(f.p.electronicSample(1,sample,at*1000,f.step()));
    auto c=f.next();CHECK(c.action==Policy::Fire);CHECK(c.deadlineUs==at+318000);f.finish(Policy::Fire);f.drain();CHECK(f.count(Policy::Fire)==1);
    CHECK(!f.p.electronicSample(1,sample,f.now*1000,f.step()));
    for(unsigned exposure:{250001u,294999u,500001u,0u}) {
        Fixture invalid;invalid.armed(true);auto bad=invalid.es(1,exposure);const uint64_t t=invalid.step();
        CHECK(!invalid.p.electronicSample(1,bad,t*1000,invalid.step()));invalid.drain();CHECK(invalid.count(Policy::Fire)==0);
    }
    Fixture high;high.armed(true);sample=high.es();sample.exposure_high=1;at=high.step();CHECK(!high.p.electronicSample(1,sample,at*1000,high.step()));
    Fixture end;end.armed(true);sample=end.es();at=end.step();CHECK(end.p.electronicSample(1,sample,at*1000,end.step()));
    CHECK(end.next().action==Policy::Fire);sample.flags=7|(2<<8);at=end.step();CHECK(!end.p.electronicSample(1,sample,at*1000,end.step()));
    CHECK(end.p.takeCancelDispatch());end.p.dispatchCancellationResult(Policy::CancelConfirmed);end.finish(Policy::Fire,false);CHECK(end.p.master);
    Fixture mode;mode.armed(false);sample=mode.es();at=mode.step();CHECK(!mode.p.electronicSample(1,sample,at*1000,mode.step()));
    Fixture stale;stale.armed(true);sample=stale.es();stale.now+=300000;CHECK(!stale.p.electronicSample(1,sample,(stale.now-250001)*1000,stale.step()));
    at=stale.now+100;CHECK(!stale.p.electronicSample(1,sample,at*1000,stale.step()));
    Fixture gate;gate.armed(true);gate.options(true,true,false);sample=gate.es();at=gate.step();CHECK(!gate.p.electronicSample(1,sample,at*1000,gate.step()));
    gate.options(true,true,true);at=gate.step();CHECK(!gate.p.electronicSample(1,sample,at*1000,gate.step()));gate.drain();CHECK(gate.count(Policy::Fire)==0);
}
static void manualTest() {
    Fixture off;CHECK(!off.p.test(off.step()));off.options(true);off.drain();
    CHECK(!off.p.test(off.step()));CHECK(off.count(Policy::Fire)==0); // 全 OFF 禁止广播。
    off.update(0,1,40);off.drain();CHECK(off.p.test(off.step()));CHECK(!off.p.test(off.step()));
    auto c=off.next();CHECK(c.action==Policy::Select);off.finish(Policy::Select);off.drain();
    CHECK(off.count(Policy::Power)==HBL_FORMAL_GROUPS+1);CHECK(off.count(Policy::Fire)==1);
    off.options(true,false,true);CHECK(off.p.test(off.step()));
    c=off.next();CHECK(c.action==Policy::Fire && c.deadlineUs==0);off.finish(Policy::Fire);off.drain();
    CHECK(off.count(Policy::Power)==HBL_FORMAL_GROUPS+1);CHECK(off.count(Policy::Fire)==2);
    off.options(true,false,false);CHECK(!off.p.test(off.step()));
    Fixture unsent;unsent.update(0,1,40);unsent.options(true,false,true);unsent.drain();
    CHECK(!unsent.p.test(unsent.step()));CHECK(unsent.p.lastError==FORMAL_GROUPS_UNSENT);CHECK(unsent.count(Policy::Fire)==0);
    Fixture active;active.armed();CHECK(!active.p.test(active.step()));
    Fixture busy;busy.options(true);busy.drain();busy.update(0,1,40);CHECK(busy.next().action==Policy::Select);CHECK(!busy.p.test(busy.step()));
    Fixture cancel;cancel.update(0,1,40);cancel.options(true);cancel.drain();CHECK(cancel.p.test(cancel.step()));cancel.options(false);cancel.drain();CHECK(cancel.count(Policy::Fire)==0);
    Fixture disabled;disabled.update(0,1,40);disabled.options(true);disabled.drain();CHECK(disabled.p.test(disabled.step()));
    CHECK(disabled.next().action==Policy::Select);disabled.update(0,0,40);disabled.finish(Policy::Select);disabled.drain();CHECK(disabled.count(Policy::Fire)==0);
    Fixture allOff;allOff.options(true);allOff.drain();CHECK(allOff.flush());allOff.drain();allOff.ack(1,FORMAL_OK);
    auto sample=allOff.mech();auto at=allOff.step();CHECK(!allOff.p.mechanicalSample(1,sample,at*1000,allOff.step()));allOff.drain();CHECK(allOff.count(Policy::Fire)==0);
}
static void configurationAndLamps() {
    Fixture f;f.armed();auto sample=f.mech();auto at=f.step();CHECK(f.p.mechanicalSample(1,sample,at*1000,f.step()));
    CHECK(f.next().action==Policy::Fire);CHECK(f.p.setWireless(32,0,f.step()));CHECK(f.p.takeCancelDispatch());
    f.p.dispatchCancellationResult(Policy::CancelConfirmed);f.finish(Policy::Fire,false);
    CHECK(f.next().action==Policy::Close);f.finish(Policy::Close);CHECK(f.next().action==Policy::Open);f.finish(Policy::Open);
    CHECK(f.p.master && f.p.restored() && f.p.channel==32 && f.p.wirelessId==0 && !f.p.shotActive);
    at=f.step();CHECK(!f.p.mechanicalSample(1,sample,at*1000,f.step()));CHECK(f.next().action==Policy::None);
    Fixture queued;queued.options(true);queued.drain();queued.update(15,1,45);CHECK(queued.next().action==Policy::Select);
    CHECK(queued.p.setWireless(1,99,queued.step()));queued.finish(Policy::Select);queued.drain();
    CHECK(queued.count(Policy::Power)==0 && queued.count(Policy::Fire)==0 && queued.p.restored());
    queued.options(true,false,false);queued.drain();CHECK(queued.p.updateLamp(15,1,queued.step()));queued.drain();
    CHECK(queued.count(Policy::Power)==1 && queued.count(Policy::Fire)==0);
    bool found=false;for(auto c:queued.log) if(c.action==Policy::Select && c.wave==HBL_FORMAL_LAMP_BASE+31) found=true;CHECK(found);
    CHECK(!queued.p.setWireless(0,0,queued.step()) && !queued.p.setWireless(33,0,queued.step()) && !queued.p.setWireless(1,100,queued.step()));
    CHECK(!queued.p.updateLamp(16,1,queued.step()) && !queued.p.updateLamp(0,2,queued.step()));
}
static void acknowledgements() {
    Fixture f;
    for(unsigned i=1;i<=33;++i) CHECK(f.flush(i));
    CHECK(!f.p.master);CHECK(f.p.lastError==FORMAL_UNAVAILABLE);
    for(unsigned i=1;i<=32;++i) f.ack(i,FORMAL_OK);
    f.noAck();CHECK(f.flush(34));f.ack(34,FORMAL_OK);f.noAck();
    Fixture active;active.options(true);active.drain();CHECK(active.flush());
    for(unsigned i=2;i<=34;++i) CHECK(!active.flush(i));
    CHECK(!active.p.master);CHECK(!active.p.shotActive);CHECK(!active.p.flushing);active.drain();CHECK(active.count(Policy::Fire)==0);
    for(unsigned i=2;i<=33;++i) active.ack(i,FORMAL_REJECTED);active.noAck();
}
static void randomizedGates() {
    // 确定性对抗交错：不模拟设备，只检查发出动作时的真实门控与buffer顺序。
    Fixture f;uint32_t random=0x61a50d34;unsigned nextToken=1;
    Policy::Command pending;bool needsRestore=false;
    for(unsigned iteration=0;iteration<10000;++iteration) {
        random^=random<<13;random^=random>>17;random^=random<<5;
        switch(random%9) {
        case 0:f.options(random&8,random&16,random&32);break;
        case 1:f.update((random>>4)%HBL_FORMAL_GROUPS,(random>>12)&1,(random>>16)%81);break;
        case 2:f.flush(nextToken++);break;
        case 3:if(f.p.token) f.p.cancel(f.p.token,f.step());break;
        case 4:if(f.p.token) f.p.endShot(f.p.token,f.step());break;
        case 5:f.p.test(f.step());break;
        case 6:f.now+=300000;f.p.tick(f.step());break;
        case 7:if((random&255)==7) f.p.disconnect(f.step());break;
        default:break;
        }
        if(f.p.takeCancelDispatch()) f.p.dispatchCancellationResult(Policy::CancelConfirmed);
        Policy::Ack ack;while(f.p.popAck(&ack)) CHECK(ack.token>0 && ack.result<=FORMAL_GROUPS_UNSENT);
        if(pending.action!=Policy::None) {
            const bool ok=(random%11)!=0;
            f.finish(pending.action,ok);
            if(pending.action==Policy::Power && ok) needsRestore=true;
            if(pending.action==Policy::Restore || !ok) needsRestore=false;
            pending=Policy::Command();
        } else {
            pending=f.next();
            if(pending.action==Policy::Power) CHECK(f.p.master && f.p.powerUpdates && !needsRestore);
            if(pending.action==Policy::Fire) CHECK(f.p.master && f.p.flashSync && f.p.eventAlive && !needsRestore);
            if(needsRestore) CHECK(pending.action==Policy::Restore);
        }
    }
}
int main() {
    schema();gates();bufferAndQueue();flushCompletion();cancellationAndFaults();mechanicalTiming();electronicTiming();manualTest();configurationAndLamps();acknowledgements();randomizedGates();
    std::printf("formal-policy-checks=%u hardware-requests=0\n",checks);return 0;
}
