"""在独立永久版中连接设置保存；锚点漂移即停止。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
path=HERE/'native/formal_runtime.cpp'
text=path.read_text(encoding='utf-8')
def once(old,new):
    global text
    if text.count(old)!=1:raise RuntimeError('settings anchor drift: '+old[:80])
    text=text.replace(old,new,1)
once('#include "formal_bridge.h"','#include "formal_bridge.h"\n#include "persistent_settings_store.h"')
once('        session=uint32_t(rf_monotonic_ms())', '''        const char *persistent=std::getenv("HBL_PERSISTENT_SETTINGS");
        persistence=persistent && !std::strcmp(persistent,"1");
        if(persistence) {
            const int loaded=HblSettingsStore::load(&saved);
            if(loaded<0) settingsError=QStringLiteral("设置读取失败，当前使用默认值");
            restoreStage=1;
        }
        power=(saved.flags&HblPersistentSettings::Power)!=0;
        sync=(saved.flags&HblPersistentSettings::Sync)!=0;
        for(unsigned i=0;i<5;++i)calibration[i]=saved.calibration[i];
        session=uint32_t(rf_monotonic_ms())''')
once('insert(QStringLiteral("sendPowerUpdates"),true); insert(QStringLiteral("sendFlashSync"),true);','insert(QStringLiteral("sendPowerUpdates"),power); insert(QStringLiteral("sendFlashSync"),sync);')
once('insert(QStringLiteral("adjustmentThirds"),true);','''insert(QStringLiteral("adjustmentThirds"),bool(saved.flags&HblPersistentSettings::Thirds));
        insert(QStringLiteral("visibleGroupMask"),int(saved.visible));
        insert(QStringLiteral("settingsError"),settingsError);
        insert(QStringLiteral("settingsRestoring"),restoreStage!=0);''')
once('insert(QStringLiteral("channel"),5); insert(QStringLiteral("wirelessId"),5);','insert(QStringLiteral("channel"),int(saved.channel)); insert(QStringLiteral("wirelessId"),int(saved.id));')
once('for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) { active[i]=0; tenths[i]=40; publishGroup(i); }','for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) { active[i]=saved.active[i]; tenths[i]=saved.tenths[i]; lamps[i]=saved.lamps[i]; publishGroup(i); }')
once('            updateHold();\n            if(connected', '            updateHold();\n            advanceRestore();\n            if(connected')
once('        const QByteArray bytes=input.toString().toUtf8();','        if(restoreStage) return QVariant();\n        const QByteArray bytes=input.toString().toUtf8();')
once('            const bool nextMaster=o.value("master").toBool();','''            const bool nextMaster=o.value("master").toBool();
            auto next=saved;next.flags=(saved.flags&HblPersistentSettings::Thirds) |
                (nextMaster ? unsigned(HblPersistentSettings::Master):0u) |
                (o.value("power").toBool() ? unsigned(HblPersistentSettings::Power):0u) |
                (o.value("sync").toBool() ? unsigned(HblPersistentSettings::Sync):0u);
            if(!saveSettings(next))return QVariant();''')
once('            // 仅保留本次界面调节偏好；不因此改变功率或提交无线请求。','''            auto next=saved;
            if(o.value("thirds").toBool())next.flags|=HblPersistentSettings::Thirds;else next.flags&=~HblPersistentSettings::Thirds;
            if(!saveSettings(next))return QVariant();
            // 保存调节偏好；不因此改变功率或提交无线请求。''')
once('        } else if(op==QStringLiteral("calibration")) {','''        } else if(op==QStringLiteral("visible")) {
            uint64_t mask=0;
            if(o.size()!=2 || !integer(o,"mask",65535,&mask))return QVariant();
            auto next=saved;next.visible=uint32_t(mask);
            if(!saveSettings(next))return QVariant();
            insert(QStringLiteral("visibleGroupMask"),int(mask));
        } else if(op==QStringLiteral("calibration")) {''')
once('            if(!hbl_calibration_valid(candidate)) return QVariant();','''            if(!hbl_calibration_valid(candidate)) return QVariant();
            auto next=saved;for(unsigned i=0;i<5;++i)next.calibration[i]=candidate[i];
            if(!saveSettings(next))return QVariant();''')
once('            if(!connected) return QVariant();\n            cancelPending', '''            if(!connected) return QVariant();
            auto next=saved;next.channel=uint32_t(channel);next.id=uint32_t(id);
            if(!saveSettings(next))return QVariant();
            cancelPending''')
once('            lamps[group]=o.value("on").toBool();publishGroup(unsigned(group));','''            auto next=saved;next.lamps[group]=o.value("on").toBool();
            if(!saveSettings(next))return QVariant();
            lamps[group]=o.value("on").toBool();publishGroup(unsigned(group));''')
once('            active[group]=o.value("active").toBool(); tenths[group]=uint32_t(powerValue); publishGroup(unsigned(group));','''            auto next=saved;next.active[group]=o.value("active").toBool();next.tenths[group]=uint32_t(powerValue);
            if(!saveSettings(next))return QVariant();
            active[group]=o.value("active").toBool(); tenths[group]=uint32_t(powerValue); publishGroup(unsigned(group));''')
once('private:\n    uint64_t holdDeadline=0;', '''private:
    HblPersistentSettings saved=HblPersistentSettings::defaults();
    bool persistence=false;
    unsigned restoreStage=0;
    uint64_t restoreAt=0;
    QString settingsError;
    bool saveSettings(const HblPersistentSettings &next) {
        if(!next.valid())return false;
        uint8_t before[HblPersistentSettings::Bytes],after[HblPersistentSettings::Bytes];
        if(!saved.encode(before,sizeof(before)) || !next.encode(after,sizeof(after)))return false;
        if(!std::memcmp(before,after,sizeof(before)))return true;
        if(persistence && !HblSettingsStore::save(next)) {
            settingsError=QStringLiteral("设置保存失败，请重新修改后确认");
            insert(QStringLiteral("settingsError"),settingsError);return false;
        }
        saved=next;settingsError.clear();insert(QStringLiteral("settingsError"),settingsError);return true;
    }
    void finishRestore(bool ok) {
        restoreStage=0;insert(QStringLiteral("settingsRestoring"),false);
        if(!ok) {
            masterRequested=false;masterAcknowledged=false;
            insert(QStringLiteral("masterRequested"),false);insert(QStringLiteral("masterEnabled"),false);
            settingsError=QStringLiteral("引闪设置恢复未完成，请检查后重新开启");
            insert(QStringLiteral("settingsError"),settingsError);
            if(connected)options();
        }
    }
    void advanceRestore() {
        if(!restoreStage)return;
        const uint64_t now=rf_monotonic_ms();
        if(restoreStage>1 && (now<restoreAt || now-restoreAt>=6500)){finishRestore(false);return;}
        if(restoreStage!=1 || !connected || value(QStringLiteral("installationHold")).toBool())return;
        FormalPacket p;init(p,FORMAL_WIRELESS);wirelessSequence=p.sequence;
        p.values[FV_CHANNEL]=saved.channel;p.values[FV_ID]=saved.id;
        restoreAt=now;restoreStage=2;
        insert(QStringLiteral("ready"),false);insert(QStringLiteral("busy"),true);
        if(!transmit(p)){disconnect();finishRestore(false);}
    }
    void restoreReply(const FormalPacket &p) {
        if(restoreStage==2 && p.sequence>=wirelessSequence && p.values[FV_READY] && !p.values[FV_BUSY]) {
            if(p.values[FV_ERROR]!=FORMAL_OK || p.values[FV_CHANNEL]!=saved.channel || p.values[FV_ID]!=saved.id){finishRestore(false);return;}
            masterRequested=(saved.flags&HblPersistentSettings::Master)!=0;
            insert(QStringLiteral("masterRequested"),masterRequested);
            restoreStage=3;options();
        } else if(restoreStage==3 && p.sequence>=optionsSequence &&
                  (!masterRequested || value(QStringLiteral("masterEnabled")).toBool())) {
            if(masterRequested)for(unsigned i=0;i<HBL_FORMAL_GROUPS && connected;++i)if(lamps[i]) {
                FormalPacket lamp;init(lamp,FORMAL_LAMP);lamp.values[FV_GROUP]=i;lamp.values[FV_ACTIVE]=1;
                if(!transmit(lamp))disconnect();
            }
            finishRestore(connected);
        }
    }
    uint64_t holdDeadline=0;''')
once('            if(p.kind==FORMAL_FLUSH_ACK && p.values[FV_ACK_TOKEN]==pendingToken && pendingToken) {', '''            restoreReply(p);
            if(p.kind==FORMAL_FLUSH_ACK && p.values[FV_ACK_TOKEN]==pendingToken && pendingToken) {''')
path.write_text(text,encoding='utf-8')
qml=HERE/'qml/controlscreen/NativeFlashPage.qml'
text=qml.read_text(encoding='utf-8')
once('    busy: adapter ? adapter.busy : false','    busy: adapter ? adapter.busy || adapter.settingsRestoring : false')
once('    errorText: adapter ? adapter.errorText : ""','    errorText: adapter ? (adapter.settingsError || adapter.errorText) : ""')
once('    onAdjustmentStepRequested:', '''    onVisibleGroupsRequested: {
        var mask=0;for(var i=0;i<indices.length;i++)mask|=(1<<indices[i]);send({op:"visible",mask:mask})
    }
    onAdjustmentStepRequested:''')
once('        setAdjustmentStep(adapter.adjustmentThirds,false)','''        setAdjustmentStep(adapter.adjustmentThirds,false)
        var visible=[];for(var g=0;g<16;g++)if(adapter.visibleGroupMask&(1<<g))visible.push(g)
        visibleGroups=visible''')
qml.write_text(text,encoding='utf-8')
qml=HERE/'qml/controlscreen/FlashPage.qml';text=qml.read_text(encoding='utf-8')
once('    signal adjustmentStepRequested(bool thirdStops)','    signal visibleGroupsRequested(var indices)\n    signal adjustmentStepRequested(bool thirdStops)')
once('        visibleGroups=next\n        groupAdjustmentSteps=0','        visibleGroups=next\n        visibleGroupsRequested(next)\n        groupAdjustmentSteps=0')
qml.write_text(text,encoding='utf-8')
print('Wired settings persistence and ordered startup restoration; hardware requests=0')
