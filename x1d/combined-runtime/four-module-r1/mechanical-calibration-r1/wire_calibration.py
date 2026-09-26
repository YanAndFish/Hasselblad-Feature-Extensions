"""将五点标定接入每次曝光冻结快照；一次性候选生成步骤。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent

def edit(name, old, new):
    p=HERE/'native'/name
    text=p.read_text(encoding='utf-8')
    if text.count(old)!=1: raise ValueError(name+': anchor drift '+old[:60])
    p.write_text(text.replace(old,new),encoding='utf-8',newline='\n')

def main():
    edit('formal_bridge.h','#include "godox_formal_wave.h"','#include "godox_formal_wave.h"\n#include "mechanical_calibration.h"')
    edit('formal_bridge.h','FV_CHANNEL,FV_ID,FV_LAMPS,FV_RECONFIGURING,','FV_CHANNEL,FV_ID,FV_LAMPS,FV_RECONFIGURING,\n    FV_CAL_125,FV_CAL_250,FV_CAL_500,FV_CAL_1000,FV_CAL_2000,')
    edit('formal_bridge.h','p->version=2;','p->version=3;')
    edit('formal_bridge.h','p->version!=2','p->version!=3')
    edit('formal_bridge.h','p->kind=kind;p->session=session;', 'if(kind==FORMAL_FLUSH) hbl_calibration_defaults(&p->values[FV_CAL_125]);\n    p->kind=kind;p->session=session;')
    edit('formal_bridge.h','(UINT64_C(0xffffffff)<<FV_GROUP_A_ACTIVE);','(UINT64_C(0xffffffff)<<FV_GROUP_A_ACTIVE)|(UINT64_C(31)<<FV_CAL_125);\n        if(!hbl_calibration_valid(&p->values[FV_CAL_125])) return 0;')
    edit('formal_policy.h','uint64_t nowUs) {\n        if(!requestedToken', 'uint64_t nowUs,const uint32_t *calibration=nullptr) {\n        uint32_t defaults[5];hbl_calibration_defaults(defaults);\n        const uint32_t *chosen=calibration ? calibration : defaults;\n        if(!hbl_calibration_valid(chosen)) return false;\n        if(!requestedToken')
    edit('formal_policy.h','dirty=0;exposureUs=exposure;electronic=es;flushing=true;', 'for(unsigned i=0;i<5;++i) frozenCalibration[i]=chosen[i];\n        dirty=0;exposureUs=exposure;electronic=es;flushing=true;')
    edit('formal_policy.h','uint64_t exposureUs=0;', 'uint64_t exposureUs=0;\n    uint32_t frozenCalibration[5]={5000,5000,6300,6900,6900};')
    edit('formal_policy.h','if(!formal_mechanical_delay(exposureUs,&delay))', 'if(!hbl_calibration_delay(exposureUs,frozenCalibration,&delay))')
    edit('formal_worker.cpp','p.values[FV_ELECTRONIC],groups,now);break;', 'p.values[FV_ELECTRONIC],groups,now,&p.values[FV_CAL_125]);break;')
    edit('formal_runtime.cpp','insert(QStringLiteral("channel"),5);', 'for(unsigned i=0;i<5;++i) insert(QStringLiteral("mechanicalDelay")+QString::number(i),int(calibration[i]));\n        insert(QStringLiteral("channel"),5);')
    edit('formal_runtime.cpp','} else if(op==QStringLiteral("wireless")) {', '''} else if(op==QStringLiteral("calibration")) {
            uint32_t candidate[5];
            if(o.size()!=6 || pendingToken || activeToken || value(QStringLiteral("shotActive")).toBool()) return QVariant();
            for(unsigned i=0;i<5;++i) {
                uint64_t number=0;
                if(!integer(o,QStringLiteral("delay")+QString::number(i),HBL_CALIBRATION_MAX_US,&number)) return QVariant();
                candidate[i]=uint32_t(number);
            }
            if(!hbl_calibration_valid(candidate)) return QVariant();
            for(unsigned i=0;i<5;++i) {
                calibration[i]=candidate[i];
                insert(QStringLiteral("mechanicalDelay")+QString::number(i),int(calibration[i]));
            }
        } else if(op==QStringLiteral("wireless")) {''')
    edit('formal_runtime.cpp','p.values[FV_TOKEN]=uint32_t(token); p.values[FV_ELECTRONIC]', 'for(unsigned i=0;i<5;++i) p.values[FV_CAL_125+i]=calibration[i];\n            p.values[FV_TOKEN]=uint32_t(token); p.values[FV_ELECTRONIC]')
    edit('formal_runtime.cpp','uint64_t lastReply=0,flushAt=0;', 'uint64_t lastReply=0,flushAt=0;\n    uint32_t calibration[5]={5000,5000,6300,6900,6900};')

if __name__=='__main__': main()
