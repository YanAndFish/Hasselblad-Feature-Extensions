#ifndef HBL_FORMAL_POLICY_H
#define HBL_FORMAL_POLICY_H
#include <stdint.h>
#include <string.h>
#include "formal_bridge.h"
#include "godox_formal_wave.h"
#include "mechanical_sync_wire.h"
#include "farm_sync_wire.h"

/* 原有两个 core 使用相同类型名；在各自命名空间内保留原实现。 */
namespace formal_mechanical {
#include "mechanical_rf_core.h"
}
namespace formal_electronic {
#include "rf_es_timing.h"
}

/* research/mechanical-parameters.json 的十三档。只匹配 UI 核实的名义档位；
 * 不插值，不使用 GMS1.mode 判断电子快门。1/640 允许微秒整数舍入。 */
static inline bool formal_mechanical_delay(uint64_t exposureUs,unsigned *delayUs) {
    if (!delayUs || !exposureUs) return false;
    if (exposureUs>=8000) { *delayUs=5000;return true; }
    const uint32_t exposure[]={6250,5000,4000,3125,2500,2000,1562,1563,1250,1000,800,625,500};
    const uint32_t delay[]={5000,5000,5000,5570,5980,6300,6560,6560,6750,6900,6900,6900,6900};
    for (unsigned i=0;i<sizeof(exposure)/sizeof(exposure[0]);++i)
        if(exposureUs==exposure[i]) { *delayUs=delay[i];return true; }
    return false;
}

/* 无设备和 Qt 依赖的唯一业务状态机。adapter 对每个 Action 仅提交一次，
 * complete 只接收底层真正完成的响应，绝不能把请求入队当作成功。
 * 一个 samplebuffer：每次功率发送完成后必须 Restore 成功才能继续。 */
class FormalPolicy {
public:
    enum Action { None,Open,Select,Power,Restore,Fire,Close };
    enum Cancellation { CancelEmpty=0,CancelSubmitted=1,CancelConfirmed=2,CancelFailed=3 };
    struct Group { unsigned active=0,tenths=40; };
    struct Command { Action action=None;unsigned wave=HBL_FORMAL_FIRE_INDEX;uint64_t deadlineUs=0; };
    struct Ack { uint32_t token;unsigned result; };
    bool master=false,powerUpdates=true,flashSync=true,eventAlive=true;
    bool held=false,ready=false,flushing=false,shotActive=false;
    bool reconfiguring=false;
    unsigned channel=5,wirelessId=5,dirtyLamps=0;
    bool lamps[HBL_FORMAL_GROUPS]={};
    bool stopLocked=false,stopFailed=false;
    bool installationReady;
    unsigned selected=HBL_FORMAL_WAVES,dirty=0,lastError=FORMAL_OK;
    Group groups[HBL_FORMAL_GROUPS];
    uint32_t token=0;
    uint64_t exposureUs=0;
    bool electronic=false;

    explicit FormalPolicy(bool readyForUser=true):installationReady(readyForUser) { formal_mechanical::rf_init(&mechanical,1); }
    bool busy() const { return inFlight.action!=None || workPhase || flushing || manualPending || reconfiguring; }
    bool syncPending() const { return firePending || (manualPending && !manualRemaining && !workPhase) || inFlight.action==Fire; }
    bool restored() const { return held && ready && selected==HBL_FORMAL_FIRE_INDEX && !workPhase && !reconfiguring; }
    Action activeAction() const { return inFlight.action; }
    unsigned activeWave() const { return inFlight.wave; }
    bool test(uint64_t nowUs) {
        if(!clock(nowUs) || !master || !flashSync || !eventAlive || !restored() ||
            busy() || shotActive || firePending || manualPending) return false;
        if(!activeMask(groups)) return false;
        if(!powerUpdates && !groupStatesSent(groups)) { lastError=FORMAL_GROUPS_UNSENT;return false; }
        for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) manualFrozen[i]=groups[i];
        // 试闪先同步本次全部分组，包括 OFF；不能直接用灯端可能遗留的状态广播。
        manualRemaining=powerUpdates ? HBL_FORMAL_GROUP_MASK : 0;
        manualUntil=nowUs+uint64_t(FORMAL_FLUSH_TIMEOUT_MS)*1000;
        manualPending=true;lastError=FORMAL_OK;return true;
    }
    bool setWireless(unsigned nextChannel,unsigned nextId,uint64_t nowUs) {
        if(!hbl_formal_config_valid(nextChannel,nextId) || !clock(nowUs) || stopLocked) return false;
        if(channel==nextChannel && wirelessId==nextId) return true;
        channel=nextChannel;wirelessId=nextId;dirty=dirtyLamps=0;knownGroups=0;
        abortShot(FORMAL_CANCELLED);if(workPhase) workCancelled=true;
        reconfiguring=true;ready=false;return true;
    }
    bool updateLamp(unsigned group,unsigned on,uint64_t nowUs) {
        if(group>=HBL_FORMAL_GROUPS || on>1 || !clock(nowUs)) return false;
        if(lamps[group]==bool(on)) return true;
        lamps[group]=bool(on);if(master) dirtyLamps|=1u<<group;
        return true;
    }
    bool setOptions(unsigned on,unsigned power,unsigned sync,uint64_t nowUs,uint64_t requestedUs=0) {
        if(on>1 || power>1 || sync>1 || !clock(nowUs)) return false;
        if(!requestedUs) requestedUs=nowUs;
        if(requestedUs>nowUs || (on && (stopLocked || !installationReady ||
            (installationUnlockedAt && requestedUs/1000<=installationUnlockedAt/1000)))) return false;
        const bool wasMaster=master,wasPower=powerUpdates;
        master=on;powerUpdates=power;flashSync=sync;
        if(!master) {
            if(workPhase) workCancelled=true;
            dirty=dirtyLamps=0;abortShot(FORMAL_CANCELLED);
        } else {
            if(!powerUpdates) {
                if(workPhase && !workIsLamp) workCancelled=true;
                dirty=0;
                if(manualPending) cancelFire();
                if(flushing && frozenPower) abortShot(FORMAL_CANCELLED);
            }
            if(!flashSync) { frozenSync=false;cancelFire(); }
            if(!wasMaster) { lastError=FORMAL_OK;dirty=dirtyLamps=0; }
            // 关闭期间的旧调节永不因重新打开某个偏好而补发。
            if(!wasPower && powerUpdates) dirty=0;
        }
        return true;
    }
    bool updateGroup(unsigned group,unsigned active,unsigned tenths,uint64_t nowUs) {
        if(group>=HBL_FORMAL_GROUPS || active>1 || tenths>80 || !clock(nowUs)) return false;
        if(groups[group].active==active && groups[group].tenths==tenths) return true;
        if(groups[group].active && !active) abortShot(FORMAL_CANCELLED);
        groups[group].active=active;groups[group].tenths=tenths;
        if(master && powerUpdates) dirty|=1u<<group;
        return true;
    }
    bool flush(uint32_t requestedToken,uint64_t exposure,bool es,const Group snapshot[HBL_FORMAL_GROUPS],uint64_t nowUs) {
        if(!requestedToken || !snapshot || !exposure || exposure>UINT64_C(86400000000) || !clock(nowUs)) return false;
        for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) if(snapshot[i].active>1 || snapshot[i].tenths>80) return false;
        if(requestedToken<=latestToken || flushing || shotActive || manualPending || inFlight.action==Fire || reconfiguring) { acknowledge(requestedToken,FORMAL_REJECTED);return false; }
        latestToken=requestedToken;token=requestedToken;lastError=FORMAL_OK;
        for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) { groups[i]=snapshot[i];frozen[i]=snapshot[i]; }
        dirty=0;exposureUs=exposure;electronic=es;flushing=true;
        frozenPower=master && powerUpdates;frozenSync=master && flashSync && activeMask(snapshot);
        remaining=frozenPower ? HBL_FORMAL_GROUP_MASK:0u;
        flushUntil=nowUs+uint64_t(FORMAL_FLUSH_TIMEOUT_MS)*1000;
        boundShot=0;shotFloor=lastShot;seenPhases=0;lastArrivalUs=0;consumed=false;firePending=false;
        if(master && !eventAlive) { abortShot(FORMAL_UNAVAILABLE);return true; }
        if(frozenSync && !frozenPower && !groupStatesSent(snapshot)) { abortShot(FORMAL_GROUPS_UNSENT);lastError=FORMAL_GROUPS_UNSENT;return true; }
        finishFlush(nowUs);
        return true;
    }
    bool cancel(uint32_t requestedToken,uint64_t nowUs) {
        if(!clock(nowUs) || !requestedToken || token!=requestedToken) return false;
        abortShot(FORMAL_CANCELLED);return true;
    }
    bool endShot(uint32_t requestedToken,uint64_t nowUs) {
        if(!clock(nowUs) || !requestedToken || token!=requestedToken) return false;
        if(flushing) { abortShot(FORMAL_CANCELLED);return true; }
        cancelFire();shotActive=false;token=0;return true;
    }
    void setEventAlive(bool alive,uint64_t nowUs) {
        if(!clock(nowUs)) return;
        eventAlive=alive;if(!alive) fail(FORMAL_UNAVAILABLE);
    }
    void disconnect(uint64_t nowUs) { clock(nowUs);knownGroups=0;fail(FORMAL_UNAVAILABLE); }
    void requestStop(uint64_t nowUs) {
        if(!clock(nowUs) || stopLocked) return;
        stopLocked=true;fail(FORMAL_CANCELLED);
    }
    bool unlockInstallation(uint64_t nowUs) {
        if(!clock(nowUs) || stopLocked) return false;
        if(!installationReady) { installationReady=true;installationUnlockedAt=nowUs; }
        return true;
    }
    bool canConfirmInstallationReady() const { return installationReady && !stopLocked; }
    bool stoppedSafely(bool radioHeld,bool radioBusy,bool radioReady) const {
        return stopLocked && !stopFailed && !held && !ready && !busy() && !syncPending() &&
               !radioHeld && !radioBusy && !radioReady;
    }
    void tick(uint64_t nowUs) {
        if(!clock(nowUs)) return;
        if(flushing && nowUs>=flushUntil) fail(FORMAL_TIMEOUT);
        if(manualPending && nowUs>=manualUntil) fail(FORMAL_TIMEOUT);
        if(shotActive && nowUs>=shotUntil) abortShot(FORMAL_TIMEOUT);
        finishFlush(nowUs);
    }
    bool popAck(Ack *ack) {
        if(!ack || !ackCount) return false;
        *ack=acknowledgements[ackHead];ackHead=(ackHead+1)%32;--ackCount;return true;
    }
    bool takeCancelDispatch() { bool r=cancelDispatch;cancelDispatch=false;return r; }
    void dispatchCancellationResult(unsigned result) {
        if(inFlight.action!=Fire) return;
        // 证明绑定当前一次 Fire，只有明确 Cancelled 才积累“未提交”。
        // Radio 已进入 Finishing 后的重复取消返回 Empty，不撤销已有证明。
        if(result==CancelConfirmed) cancelConfirmed=true;
        else if(result==CancelFailed || result>CancelFailed ||
                (result==CancelSubmitted && cancelConfirmed)) cancellationFailed=true;
    }
    void newSession(uint64_t nowUs) { disconnect(nowUs);latestToken=0; }

    Command next(uint64_t nowUs) {
        tick(nowUs);
        if(inFlight.action!=None) return Command();
        if(reconfiguring) {
            workPhase=0;
            if(held) return issue(Close);
            reconfiguring=false;
        }
        if(workPhase) {
            // 关闭与取消可以阻止尚未提交的功率，已发出的包只能等待响应。
            if(workPhase<3 && (workCancelled || !master || (!workIsLamp && !powerUpdates) || (workForFlush && !flushing) || (workForTest && !manualPending))) workPhase=3;
            if(workPhase==1) return issue(Select,workWave);
            if(workPhase==2) return issue(Power,workWave);
            return issue(Restore,HBL_FORMAL_FIRE_INDEX);
        }
        if(!master || (!powerUpdates && !flashSync && !dirtyLamps)) {
            if(held) return issue(Close);
            finishFlush(nowUs);return Command();
        }
        if(!held) return issue(Open);
        if(!ready || selected!=HBL_FORMAL_FIRE_INDEX) { fail(FORMAL_RADIO_ERROR);return next(nowUs); }
        if(manualPending) {
            if(manualRemaining) {
                const unsigned i=first(manualRemaining);manualRemaining&=~(1u<<i);
                beginWork(i,manualFrozen[i],false,true);return next(nowUs);
            }
            manualPending=false;return issue(Fire);
        }
        if(firePending) {
            firePending=false;
            if(!shotActive || !frozenSync || !flashSync || !eventAlive || consumed ||
                (nowUs>fireDeadline && nowUs-fireDeadline>250000)) { consumed=true;return Command(); }
            consumed=true;return issue(Fire,HBL_FORMAL_FIRE_INDEX,fireDeadline);
        }
        if(flushing) {
            if(remaining) {
                const unsigned i=first(remaining);remaining&=~(1u<<i);
                beginWork(i,frozen[i],true);return next(nowUs);
            }
            finishFlush(nowUs);
        }
        if(shotActive || flushing) return Command();
        if(dirtyLamps) {
            const unsigned i=first(dirtyLamps);dirtyLamps&=~(1u<<i);
            workGroup=i;workIsLamp=true;workForFlush=workForTest=false;workCancelled=false;workPhase=1;
            hbl_formal_lamp_index(&workWave,i,lamps[i]);return next(nowUs);
        }
        if(powerUpdates && dirty) {
            const unsigned i=first(dirty);dirty&=~(1u<<i);
            beginWork(i,groups[i],false);return next(nowUs);
        }
        return Command();
    }
    void complete(Action action,bool ok,uint64_t nowUs) {
        if(action==None || inFlight.action!=action) { fail(FORMAL_RADIO_ERROR);return; }
        inFlight=Command();
        if(!clock(nowUs)) return;
        if(action==Close) {
            held=ready=false;selected=HBL_FORMAL_WAVES;
            if(reconfiguring) knownGroups=0;
            if(!ok) { reconfiguring=false;fail(FORMAL_RADIO_ERROR);if(stopLocked) stopFailed=true; }
            finishFlush(nowUs);return;
        }
        const bool knownCancellation=action==Fire && cancelConfirmed && !cancellationFailed;
        if(action==Fire) {
            if(cancellationFailed) ok=false;
            cancelConfirmed=cancellationFailed=cancelDispatch=false;
        }
        if(action==Fire && !ok && knownCancellation) return;
        if(!ok) {
            // 失败的 open 也可能已经 hold，强制 adapter 走 close 释放。
            held=true;ready=false;selected=HBL_FORMAL_WAVES;workPhase=0;
            fail(FORMAL_RADIO_ERROR);return;
        }
        switch(action) {
        case Open:held=ready=true;selected=HBL_FORMAL_FIRE_INDEX;break;
        case Select:selected=workWave;ready=true;workPhase=2;break;
        case Power:
            if(!workIsLamp) {
                knownGroups|=1u<<workGroup;
                if(workValue.active) sentActive|=1u<<workGroup;else sentActive&=~(1u<<workGroup);
            }
            ready=true;workPhase=3;break;
        case Restore:selected=HBL_FORMAL_FIRE_INDEX;ready=true;workPhase=0;break;
        case Fire:ready=true;break;
        default:break;
        }
        finishFlush(nowUs);
    }

    bool mechanicalSample(uint32_t epoch,const HblMechanicalSync &sample,uint64_t arrivalNs,uint64_t nowUs) {
        if(!hbl_mech_fields_valid(&sample) || !prepareSample(epoch,sample.trial,arrivalNs,nowUs,false)) return false;
        if(sample.clear_flags&HBL_MECH_DONE) { cancelFire();consumed=true;return false; }
        const unsigned events=(sample.clear_flags>>8)&HBL_MECH_EVENT_MASK;
        if(!(events&~seenPhases)) return false;
        seenPhases|=events;
        if(!frozenSync || !flashSync || consumed || !restored() || busy()) return false;
        unsigned delay;
        if(!formal_mechanical_delay(exposureUs,&delay)) { consumed=true;return false; }
        formal_mechanical::rf_configure(&mechanical,1,2,delay);
        if(!formal_mechanical::mechanical_rf_accept(&mechanical,&sample,arrivalNs/1000,nowUs,armedAt)) return false;
        fireDeadline=mechanical.deadline_us;firePending=true;return true;
    }
    bool electronicSample(uint32_t epoch,const HblFarmSync &sample,uint64_t arrivalNs,uint64_t nowUs) {
        if(!hbl_sync_fields_valid(&sample) || !prepareSample(epoch,sample.shot,arrivalNs,nowUs,true)) return false;
        const unsigned source=hbl_sync_source(sample.flags);
        if(source==2) { cancelFire();consumed=true;return false; }
        if(source || (seenPhases&1)) return false;
        seenPhases|=1;
        if((sample.flags&255)!=7 || !frozenSync || !flashSync || consumed || !restored() || busy()) { consumed=true;return false; }
        unsigned delayMs;
        if(!formal_electronic::rf_es_center_delay(sample.exposure_low,sample.exposure_high,&delayMs)) { consumed=true;return false; }
        // 来自 GFS3 的当前曝光才参与电子公式，UI 名义曝光仅供机械查表。
        fireDeadline=arrivalNs/1000+uint64_t(delayMs)*1000;
        firePending=true;return true;
    }
private:
    Command inFlight;
    Group frozen[HBL_FORMAL_GROUPS],manualFrozen[HBL_FORMAL_GROUPS],workValue;
    unsigned remaining=0,manualRemaining=0,workPhase=0,workWave=0,workGroup=0,seenPhases=0,knownGroups=0,sentActive=0;
    bool workIsLamp=false,workForTest=false;
    bool workForFlush=false,workCancelled=false,frozenPower=false,frozenSync=false,firePending=false,manualPending=false;
    bool consumed=false,cancelDispatch=false,cancelConfirmed=false,cancellationFailed=false;
    uint32_t latestToken=0,syncEpoch=0,lastShot=0,boundShot=0,shotFloor=0;
    uint64_t lastNowUs=0,armedAt=0,flushUntil=0,shotUntil=0,manualUntil=0,lastArrivalUs=0,fireDeadline=0,installationUnlockedAt=0;
    formal_mechanical::RfCore mechanical;
    Ack acknowledgements[32];
    unsigned ackHead=0,ackCount=0;
    static unsigned first(unsigned mask) { for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) if(mask&(1u<<i)) return i;return 0; }
    static unsigned activeMask(const Group snapshot[HBL_FORMAL_GROUPS]) {
        unsigned mask=0;for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) if(snapshot[i].active) mask|=1u<<i;return mask;
    }
    bool groupStatesSent(const Group snapshot[HBL_FORMAL_GROUPS]) const {
        return knownGroups==HBL_FORMAL_GROUP_MASK && sentActive==activeMask(snapshot);
    }
    bool clock(uint64_t nowUs) {
        if(!nowUs || nowUs<lastNowUs) { fail(FORMAL_UNAVAILABLE);return false; }
        lastNowUs=nowUs;return true;
    }
    void acknowledge(uint32_t t,unsigned result) {
        if(!t) return;
        if(ackCount>=32) {
            master=false;dirty=dirtyLamps=0;lastError=FORMAL_UNAVAILABLE;cancelFire();
            if(workPhase) workCancelled=true;
            flushing=shotActive=false;remaining=0;token=0;frozenSync=false;return;
        }
        acknowledgements[(ackHead+ackCount)%32]=Ack{t,result};++ackCount;
    }
    void cancelFire() {
        firePending=false;manualPending=false;manualRemaining=0;formal_mechanical::rf_cancel(&mechanical);
        if(workPhase && workForTest) workCancelled=true;
        if(inFlight.action==Fire) cancelDispatch=true;
    }
    void abortShot(unsigned reason) {
        cancelFire();consumed=true;
        if(workPhase && workForFlush) workCancelled=true;
        if(flushing) acknowledge(token,reason);
        flushing=shotActive=false;remaining=0;token=0;frozenSync=false;
    }
    void fail(unsigned reason) {
        if(workPhase) workCancelled=true;
        lastError=reason;master=false;dirty=dirtyLamps=0;abortShot(reason);
    }
    void finishFlush(uint64_t nowUs) {
        if(!flushing || remaining || workPhase || inFlight.action!=None) return;
        if(master && (frozenPower || frozenSync) && !restored()) return;
        flushing=false;shotActive=master;armedAt=nowUs;shotFloor=lastShot;
        // UI ShotEnd 是正常释放入口；额外上界只用于遗失的结束信号。
        shotUntil=nowUs+exposureUs+UINT64_C(5000000);
        formal_mechanical::rf_init(&mechanical,1);
        acknowledge(token,FORMAL_OK);
        if(!master) token=0;
    }
    Command issue(Action action,unsigned wave=HBL_FORMAL_FIRE_INDEX,uint64_t deadline=0) {
        inFlight.action=action;inFlight.wave=wave;inFlight.deadlineUs=deadline;
        if(action==Fire) cancelConfirmed=cancellationFailed=false;
        if(action==Select || action==Restore || action==Open) ready=false;
        return inFlight;
    }
    void beginWork(unsigned i,const Group &value,bool forFlush,bool forTest=false) {
        hbl_formal_power_index(&workWave,i,value.active,value.tenths);
        workGroup=i;workValue=value;workIsLamp=false;workForTest=forTest;
        workForFlush=forFlush;workCancelled=false;workPhase=1;
    }
    bool prepareSample(uint32_t epoch,uint32_t shot,uint64_t arrivalNs,uint64_t nowUs,bool es) {
        if(!epoch || !shot || !clock(nowUs)) return false;
        const uint64_t at=arrivalNs/1000;
        if(!at || at>nowUs || nowUs-at>250000) return false;
        if(syncEpoch && syncEpoch!=epoch) {
            syncEpoch=epoch;lastShot=shot;fail(FORMAL_UNAVAILABLE);return false;
        }
        syncEpoch=epoch;
        if(shot<lastShot) return false;
        lastShot=shot;
        if(!master || !eventAlive || !shotActive || shot<=shotFloor || es!=electronic || at<armedAt || at<lastArrivalUs) return false;
        if(boundShot && boundShot!=shot) { cancelFire();consumed=true;return false; }
        boundShot=shot;lastArrivalUs=at;return true;
    }
};
/* worker 与测试共用的取消转接。返回值保留 Empty/Submitted/Cancelled/Failed
 * 四类结果，不压缩成会丢失“重复取消”含义的 bool。 */
template<class Radio>
static inline unsigned formal_cancel_pending(FormalPolicy &policy,Radio &radio) {
    const unsigned result=unsigned(radio.cancelPending());
    policy.dispatchCancellationResult(result);return result;
}
#endif
