"""离线核对当前唯一 D 组普通引闪波形；不导出空中报文字节，不访问设备。"""
from pathlib import Path
import hashlib
import json
import struct

HERE=Path(__file__).resolve().parents[1]

def audit():
    path=HERE/'build/prepared-wltest.bin'
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    if digest!='654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688':
        raise RuntimeError('Prepared radio baseline changed')
    runs=[struct.unpack_from('<HHI',data,0x215c00-0x180000+8*i) for i in range(96)]
    steps=sorted({r[2] for r in runs})
    assert len(steps)==2 and all(r[1]==0 and r[0] in (160,161) for r in runs)
    bits=[1-steps.index(r[2]) for r in runs]
    frame=bytes(sum(bits[i+j]<<(7-j) for j in range(8)) for i in range(0,96,8))
    assert frame[:4] in (b'\xaa'*4,b'\x55'*4)
    assert frame[4:8]==(0xc368//6).to_bytes(2,'big')*2
    # 与原先 AD400Pro v1.50 普通 D 组分支核对结果绑定。
    # 完整业务字段是帧头、D组地址、普通触发命令、普通触发值，没有附加参数包。
    assert frame[8:]==bytes((0xa9,0x0d,0xb4,9))
    report={'passed':True,'firmwareSha256':digest,'packets':1,'modulatedBits':96,
        'preambleBytes':4,'idSyncBytes':4,'commandBytes':4,'targetGroup':'D','targetId':5,'targetChannel':5,
        'flashPowerParameterPackets':0,'multiParameterPackets':0,'additionalControlPackets':0,
        'sampleCountForModulatedBits':sum(r[0] for r in runs),'waveformChanged':False,'hardwareRequests':0,
        'evidenceLimit':'固定候选的离线反解；不等于新空中抓包，也不证明可删除接收端必需字段。'}
    (HERE/'research/waveform-payload-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__': print(json.dumps(audit(),ensure_ascii=False))
