"""固定 FARM 中的两项 AF 任务、CV IRQ 和记录写者来源；只读固件。"""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication

def main():
    f=FarmApplication();assert f.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    targets={a:[] for a in (0x1a1a98,0x1a1cd8,0x1a2a30,0x1f0c20)}
    for offset in range(0,0x14a000,4):
        word=struct.unpack_from('<I',f.data,offset)[0]
        if word&0x0f000000!=0x0b000000:continue
        delta=word&0xffffff
        if delta&0x800000:delta-=0x1000000
        destination=0x100000+offset+8+4*delta
        if destination in targets:targets[destination].append(0x100000+offset)
    assert targets[0x1a1a98]==[0x19b454] and targets[0x1a1cd8]==[0x19b464]
    assert targets[0x1a2a30]==[0x1a1cc0,0x1a22a8] and targets[0x1f0c20]==[0x19870c]
    assert f.read(0x247a0c,11)==b'AF_SERVICE\0' and f.read(0x247a3c,14)==b'AF_SERVICE_SM\0'
    regions=[('task_creation',0x1a44f8,0x1a4618),('data_dispatch',0x19b284,0x19b46c),
        ('control_wait',0x19b708,0x19b77c),('cv_irq',0x1986d8,0x198778),
        ('irq_context',0x100770,0x1007ec),('probe_command',0x1a1f34,0x1a1f78)]
    out=HERE/'build/native-task-study';out.mkdir(parents=True,exist_ok=True)
    evidence={'kind':'native-af-task-ownership','baselineSha256':f.sha256,'hardwareRequests':0,
        'tasks':[{'name':'AF_SERVICE','entry':0x19b284,'createCall':0x1a4530,'priority':4},
                 {'name':'AF_SERVICE_SM','entry':0x19b708,'createCall':0x1a4610,'priority':4}],
        'directCallers':{hex(a):v for a,v in targets.items()},
        'recordOwnership':{'irq':'CV IRQ -> 0x1f0c20 -> nc_raw',
            'data':'AF_SERVICE -> CV/position FIFO, accepted values, probe speed',
            'control':'AF_SERVICE_SM -> cycle reset, fast/fine speed'},
        'regions':[{'name':name,'start':a,'endExclusive':b,'sha256':hashlib.sha256(f.read(a,b-a)).hexdigest()} for name,a,b in regions],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limitations':['静态任务创建和直接调用证据；不证明真实调度时刻','单写者分环解决日志覆盖，不证明物理帧关联或对焦算法的并发提供器已实现']}
    (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'evidence.asm').write_text('\n\n'.join('; '+name+'\n'+f.disassembly(a,b-a) for name,a,b in regions),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':main()
