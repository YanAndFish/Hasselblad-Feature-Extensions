"""双 IRQ 配置的离线差量与逆向恢复计划；没有 USB、PCAP 或实机执行入口。"""
from pathlib import Path
import hashlib
import json
import struct

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-irq-candidate'
BASE_SHA='8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30'
FARM_SHA='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'

def digest(data): return hashlib.sha256(data).hexdigest()

def apply_image(image,plan,restore=False):
    """只接受完整、完全匹配的主机字节；不能给它设备对象或局部内存快照。"""
    if type(image) is not bytes or len(image)!=plan['bytes']:
        raise ValueError('必须提供完整离线配置字节')
    before=plan['candidateSha256'] if restore else plan['baselineSha256']
    after=plan['baselineSha256'] if restore else plan['candidateSha256']
    if digest(image)!=before: raise ValueError('配置不是要求的完整基线')
    result=bytearray(image); seen=set()
    for row in plan['words']:
        offset=row['offset']; old=row['after'] if restore else row['before']; new=row['before'] if restore else row['after']
        if type(offset) is not int or offset%4 or not 0<=offset<=len(image)-4 or offset in seen:
            raise ValueError('差量边界或重复项错误')
        if struct.unpack_from('<I',image,offset)[0]!=old: raise ValueError('原字节不匹配')
        struct.pack_into('<I',result,offset,new); seen.add(offset)
    if digest(result)!=after: raise ValueError('差量结果完整哈希不匹配')
    return bytes(result)

def build(raw,farm):
    assert Path.cwd().resolve()==HERE.parents[1]
    assert digest(raw)==BASE_SHA and farm.sha256==FARM_SHA
    candidate=(OUT/'irq-pl-candidate.bin').read_bytes()
    built=json.loads((OUT/'fpga-build.json').read_text(encoding='utf-8'))
    assert built['candidateSha256']==digest(candidate) and len(candidate)==len(raw) and len(raw)%4==0
    words=[{'offset':i,'before':struct.unpack_from('<I',raw,i)[0],
            'after':struct.unpack_from('<I',candidate,i)[0]}
           for i in range(0,len(raw),4) if raw[i:i+4]!=candidate[i:i+4]]
    plan={'kind':'offline-complete-image-delta','bytes':len(raw),'baselineSha256':BASE_SHA,
        'candidateSha256':digest(candidate),'changedWords':len(words),'words':words,
        'installed':False,'hardwareRequests':0,'liveLoaderEnabled':False,
        'requiresExactFullBaselineBeforeAnyWrite':True,'partialReconfigurationImage':False}
    assert apply_image(raw,plan)==candidate and apply_image(candidate,plan,True)==raw
    # 固定原厂机器码锚点；不能把官方版本分析当作实机版本读取。
    checks={
        0x1e2158:('movw','r2, #0x21b'),0x1e2264:('bl','#0x1e1964'),
        0x1e19b8:('cmp','r3, #1'),0x1e19c0:('bl','#0x22e6e4'),
        0x22e6fc:('bl','#0x22a9a4'),0x22e724:('bl','#0x22cc4c'),0x22e730:('bl','#0x22aa98'),
        0x22ceb8:('bl','#0x22b800'),0x22cebc:('mov','r0, #1'),
        0x22b910:('bl','#0x22b4fc'),0x22b924:('bl','#0x21f5d4'),
        0x21f620:('mov','r3, #0x2100000'),0x21f624:('add','r3, r3, #0x29000'),
        0x21f628:('ldr','r3, [r3, #8]'),0x21f640:('ldr','r3, [r3, #4]'),
        0x21f644:('lsr','r2, r3, #2'),0x22ba94:('bl','#0x104358'),
        0x22d0bc:('blx','r4'),0x22b6e0:('bne','#0x22b6c0'),
        0x22b730:('beq','#0x22b710'),0x22b754:('blt','#0x22b738'),
        0x22cdb0:('beq','#0x22cd90')}
    evidence=[]
    for address,wanted in checks.items():
        ins=farm.instructions(address,4)[0]
        assert (ins.mnemonic,ins.op_str)==wanted,(hex(address),ins.mnemonic,ins.op_str)
        evidence.append({'address':hex(address),'bytes':ins.bytes.hex(),'mnemonic':ins.mnemonic,'operands':ins.op_str})
    pcap=json.loads((OUT/'pcap-validation.json').read_text(encoding='utf-8'))
    assert pcap['passed'] and pcap['firmwareSha256']==FARM_SHA
    report={'offlineDeltaBuilt':True,'roundTripExact':True,'changedWords':len(words),'changedFrames':built['changedFrameCount'],
        'hardwareRequests':0,'installed':False,'firmwareSha256':FARM_SHA,'instructionChecks':evidence,
        'cachedDescriptor':'0x02129000','liveCachedPointerRead':False,'liveCachedImageHashVerified':False,
        'configurationScope':'full-PL-reset-and-resource-reinitialization',
        'originalWrapperIgnoresDownloadReturn':True,'resetHandshakeHasUnboundedWait':True,
        'liveLoaderReady':False,
        'remaining':['核对当前 RAM 中缓存配置的完整内容与地址寿命。',
            '补齐复位握手及资源恢复失败路径，不能由通用 IRQ 缓存 thunk 直接执行会等待的原厂任务函数。',
            '解除旧采集版本、注册新 IRQ、配置装载及逆向恢复的组合故障模型。',
            '目标 Qt 自检和硬件时序仍未验证。'],
        'sourceSha256':digest(Path(__file__).read_bytes()),
        'registerReference':'https://raw.githubusercontent.com/Xilinx/embeddedsw/xilinx-v2017.2/XilinxProcessorIPLib/drivers/devcfg/src/xdevcfg_hw.h'}
    (OUT/'irq-pl-word-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'loading-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    from mechanical_fpga_route import load
    route,_,_=load()
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(build(bytes(next(iter(route.frames.values())).obj),FarmApplication()),ensure_ascii=False))
