"""仅构建临时时间线候选，不安装、不改变引闪决策。"""
from pathlib import Path
import hashlib, json, os, subprocess, sys
sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
ROOT = P.parents[3]
assert Path.cwd().resolve() == ROOT
OUT = P / 'build/flash-timeline-probe'
OUT.mkdir(parents=True, exist_ok=True)
source = (P / 'native/formal_worker.cpp').read_text(encoding='utf-8')
def replace(old, new):
    global source
    assert source.count(old) == 1, old
    source = source.replace(old, new)

# 所有记录点与工作器处于同一线程。固定数组满后停止，不覆盖证据。
replace('    bool enableConfirmedWritten=false;', '''    bool enableConfirmedWritten=false;
    struct ProbeRow { uint64_t at, sourceAt; unsigned kind, value, result, flags, wave; };
    ProbeRow probeRows[8192]={};
    unsigned probeCount=0;
    uint64_t probeStart=0;
    bool probeSaved=false;
    void probe(unsigned kind,unsigned value,unsigned result,uint64_t sourceAt=0) {
        if(probeSaved || probeCount>=8192 || (!probeStart && kind!=1)) return;
        const uint64_t now=formalNowUs();
        if(!probeStart) probeStart=now;
        probeRows[probeCount++]={now,sourceAt,kind,value,result,
            unsigned(policy.flushing)|(unsigned(policy.shotActive)<<1)|
            (unsigned(policy.busy())<<2)|(unsigned(policy.restored())<<3)|
            (unsigned(radio.busy)<<4)|(unsigned(policy.master)<<5),policy.activeWave()};
    }
    void saveProbe(uint64_t now) {
        // 只在五分钟结束且没有当前拍摄/发送任务时落盘。
        if(probeSaved || !probeStart || now-probeStart<UINT64_C(300000000) ||
           policy.busy() || policy.shotActive || policy.syncPending()) return;
        probeSaved=true;
        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/flash-timeline.tsv"));
        if(!file.open(QIODevice::WriteOnly)) return;
        file.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner);
        file.write("at_us\\tsource_ns\\tkind\\tvalue\\tresult\\tflags\\twave\\n");
        for(unsigned i=0;i<probeCount;++i) {
            const ProbeRow &r=probeRows[i];
            const QByteArray line=QByteArray::number(qulonglong(r.at))+"\\t"+
                QByteArray::number(qulonglong(r.sourceAt))+"\\t"+QByteArray::number(r.kind)+"\\t"+
                QByteArray::number(r.value)+"\\t"+QByteArray::number(r.result)+"\\t"+
                QByteArray::number(r.flags)+"\\t"+QByteArray::number(r.wave)+"\\n";
            file.write(line);
        }
        file.commit();
    }''')
replace('            policy.complete(action,ok,formalNowUs());pump();',
        '            probe(3,unsigned(action),unsigned(ok));policy.complete(action,ok,formalNowUs());pump();')
replace('            reportStopResult();', '            reportStopResult();saveProbe(now);')
replace('            policy.mechanicalSample(epoch,sample,arrivalNs,formalNowUs());pump();return;',
        '            probe(4,sample.trial,0,arrivalNs);const bool accepted=policy.mechanicalSample(epoch,sample,arrivalNs,formalNowUs());probe(5,sample.trial,unsigned(accepted),arrivalNs);pump();return;')
replace('            policy.electronicSample(epoch,sample,arrivalNs,formalNowUs());pump();return;',
        '            probe(6,sample.shot,0,arrivalNs);const bool accepted=policy.electronicSample(epoch,sample,arrivalNs,formalNowUs());probe(7,sample.shot,unsigned(accepted),arrivalNs);pump();return;')
replace('            if(command.action==FormalPolicy::None) break;',
        '            if(command.action==FormalPolicy::None) break;probe(2,unsigned(command.action),0);')
replace('        while(policy.popAck(&ack)) status(FORMAL_FLUSH_ACK,ack.token,ack.result);',
        '        while(policy.popAck(&ack)) { probe(8,ack.token,ack.result);status(FORMAL_FLUSH_ACK,ack.token,ack.result); }')
replace('            case FORMAL_FLUSH: {', '            case FORMAL_FLUSH: { probe(1,p.values[FV_TOKEN],0);')
generated = OUT / 'formal_worker.cpp'
generated.write_text(source, encoding='utf-8', newline='\n')
reference = json.loads((P / 'build/combined-hub/runtime-build.json').read_text())
for name, digest in reference['sources'].items():
    assert hashlib.sha256((P/name).read_bytes()).hexdigest() == digest, name
zig = ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
env = dict(os.environ)
for key, name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
    d=OUT/name;d.mkdir(exist_ok=True);env[key]=str(d)
commands=[]
for old in reference['commands']:
    args=[]
    for value in old['arguments']:
        if Path(value).name == 'formal_worker.cpp': value=str(generated)
        elif value.endswith(('.o','.so')) and 'combined-hub' in value: value=str(OUT/Path(value).name)
        args.append(value)
    if '-c' in args: args[1:1]=['-I'+str(P/'native')]
    r=subprocess.run([str(zig)]+args,cwd=ROOT,env=env,capture_output=True,text=True)
    commands.append({'arguments':args,'exit':r.returncode,'stderr':r.stderr})
    if r.returncode: print(r.stderr);r.check_returncode()
binary=OUT/'libhbl-combined-loader.so'
(OUT/'build.json').write_text(json.dumps({'passed':True,'installed':False,'commands':commands,
    'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'bytes':binary.stat().st_size},indent=2),encoding='utf-8')
print(json.dumps({'built':True,'installed':False,'bytes':binary.stat().st_size}))
