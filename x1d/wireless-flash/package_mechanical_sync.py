"""机械七信号临时包；校验、生成与归档均在电脑完成，不自动安装。"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-sync-candidate'

def sha(data): return hashlib.sha256(data).hexdigest()

def package():
    assert Path.cwd().resolve()==ROOT
    sys.path.insert(0,str(HERE/'research'))
    import mechanical_sync_loader as loader
    if not loader.offline_ready(): raise RuntimeError('Current offline evidence does not match')
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    names=('libhbl-wireless.so','wireless-worker','ui.rcc','prepare-radio.sh','libhbl-mechanical-observer.so','mechanical-sync-hook-check')
    files={name:(OUT/name).read_bytes() for name in names}
    probe=(HERE/'build/netlink-probe').read_bytes()
    if sha(probe)!='a850123f1d67c553e073c00a2fc8fc3e34c45942e4c3b385a12055387df37741':
        raise RuntimeError('Fixed non-transmitting probe changed')
    files['netlink-probe']=probe
    for name in ('install','restore'):
        s=(HERE/('fpga-sync-'+name+'.sh')).read_text(encoding='utf-8')
        for old,new in [('GFS1','GMS1'),('80-hbl-fpga-sync.conf','80-hbl-mechanical-sync.conf'),
                        ('farm-sync-hook-check','mechanical-sync-hook-check'),('HBL_FARM_SYNC','HBL_MECHANICAL_SYNC'),
                        ('libhbl-farm-sync-observer.so','libhbl-mechanical-observer.so'),('fpga-sync.sock','mechanical-sync.sock'),
                        ('fpga-sync.ready','mechanical-sync.ready'),('sync-observer.status','mechanical-observer.status'),
                        ('fpga-sync-restore.sh','mechanical-sync-restore.sh')]: s=s.replace(old,new)
        if name=='install':
            anchor='"$d/wireless-worker" --check-slots || exit 68'
            if s.count(anchor)!=1: raise RuntimeError('Missing worker preflight anchor')
            s=s.replace(anchor,anchor+'\n"$d/wireless-worker" --check-timer || exit 68')
        path=HERE/('mechanical-sync-'+name+'.sh')
        path.write_text(s,encoding='utf-8',newline='\n')
        files[path.name]=path.read_bytes()
    files['release-radio.sh']=(HERE/'release-radio.sh').read_bytes().replace(b'\r\n',b'\n')
    for index in range(3): files['delta/'+str(index)+'.bin']=(HERE/'build/delta'/(str(index)+'.bin')).read_bytes()
    bash=Path('C:/Program Files/Git/bin/bash.exe')
    for name in files:
        if name.endswith('.sh'):
            path=OUT/name if (OUT/name).exists() else HERE/name
            subprocess.run([str(bash),'--noprofile','--norc','-n',str(path)],check=True,timeout=10)
    files['manifest.sha256']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode('ascii')
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in sorted(files.items()):
            entry=tarfile.TarInfo(name); entry.mode=0o600; entry.size=len(data); entry.mtime=0
            archive.addfile(entry,io.BytesIO(data))
    packed=gzip.compress(raw.getvalue(),mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as archive:
        assert {e.name for e in archive}==set(files)
        for e in archive:
            assert e.isfile() and e.mode==0o600 and archive.extractfile(e).read()==files[e.name]
    (OUT/'session-package.tar.gz').write_bytes(packed)
    report={'status':'离线候选已封装，待机内 Qt 检查与安装','installed':False,'hardwareRequests':0,
            'packageSha256':sha(packed),'packageBytes':len(packed),'farmPayloadSha256':loader.PAYLOAD_SHA,
            'files':{name:{'sha256':sha(data),'bytes':len(data)} for name,data in files.items()},
            'checks':{'hostSevenSourceWire':True,'armSimulation':8,'armTarget':8,'loaderTests':7,
                      'loaderFaultPositions':1698,'fpgaCases':8,'shellSyntax':True,'archiveRoundtrip':True,'targetQt':False},
            'restoreOrder':'先停止无线 worker，再解除并核对 FARM 五处原指令，最后移除消息接收覆盖；载荷保留到手动重启。',
            'timingLimit':'七项均为 FPGA 状态观测，部分可同次出现。延迟从 Linux 消息接收时刻计算；不代表物理曝光沿或实测精度。',
            'physicalTimingMeasured':False,'agentFlashTrials':0,'cameraShotsTriggered':0}
    (OUT/'package-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'packageBytes':len(packed),'members':len(files),'offlinePassed':True,'installed':False}

if __name__=='__main__': print(package())
