"""固定原厂镜头 AFSYNC → 位置消息与机身 CV/FIFO 的离线证据。"""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
sys.path[:0]=[str(ROOT/'.research-cache/x1d-1.25.0/python'),str(ROOT/'x1d/tools'),str(ROOT/'x1d/wireless-flash/research')]
from lens_flash_sync import SharedLensImage,HEX_SHA,IMAGE_SHA
from farm_diagnostic_binary import FarmApplication

LENS_REGIONS=[('registration',0x4974,0x49dc),('main_context',0x17a4e,0x17a7e),
 ('focus_callbacks',0x1b8cc,0x1b8f8),('interface_init',0x20c20,0x20dbc),
 ('afsync_registration_call',0x215d8,0x216d0),('afsync_dispatch',0x29468,0x2946e),
 ('focus_afsync',0x1a150,0x1a204),('position_getters',0x19b00,0x19b68),
 ('position_normalization',0x287a6,0x287e0),('feedback_route',0x20b58,0x20b8c),
 ('feedback_packet',0x21538,0x215a0)]
FARM_REGIONS=[('cv_interrupt_registration',0x1a46b4,0x1a4700),
 ('cv_irq',0x1986d8,0x198778),('cv_read',0x1f0c20,0x1f0e6c),
 ('cv_fifo',0x1a1a98,0x1a1cd4),('position_fifo',0x1a1cd8,0x1a22bc),
 ('native_pairing',0x1a2a30,0x1a3168)]

def main():
    lens=SharedLensImage();farm=FarmApplication()
    assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    table=lens.word(0x1b8ec);callback=lens.initial_word(table+0x28)
    assert (table,callback,lens.word(0x216cc))==(0x20201a44,0x1a151,0x29469)
    output=HERE/'build/native-afsync-study';output.mkdir(parents=True,exist_ok=True)
    regions=[];text=[]
    for origin,source,ranges in [('lens-1.9.11',lens,LENS_REGIONS),('farm-1.25.0',farm,FARM_REGIONS)]:
        for name,start,end in ranges:
            blob=source.read(start,end-start)
            regions.append({'origin':origin,'name':name,'start':start,'endExclusive':end,'sha256':hashlib.sha256(blob).hexdigest()})
            asm='\n'.join(f'{i.address:08x}: {i.mnemonic} {i.op_str}' for i in source.instructions(start,end-start)) if origin.startswith('lens') else source.disassembly(start,end-start)
            text.append(f'; {origin} {name}\n'+asm)
    report={'kind':'offline-afsync-evidence','hardwareRequests':0,'farmSha256':farm.sha256,
        'sharedLensHexSha256':HEX_SHA,'sharedLensImageSha256':IMAGE_SHA,
        'lensTableInitialTemplate':table,'callbackThumb':callback,'regions':regions,
        'verifiedStaticFacts':[
            '镜头 AFSYNC 注册回调 0x29469 分发到对象 +0x4c 的表 +0x28；固定初始化模板为 0x1a151。',
            '0x1a150 回调先取位置，再把 +0x6c 序号加一并模 100，经过 0x20b58/0x21538 发送位置及序号。',
            '机身 0x1a1cd8 解码消息 +5/+6 的 signed16 位置及 +9 的序号；随后放入独立五槽位置 FIFO。',
            '机身通过 IRQ 0x59 登记 0x1986d8；该入口调用 0x1f0c20 读取 FPGA 两个统计通道并发布仅含单一 CV 的 0xCC 消息。',
            'CV 入五槽 FIFO 前有首个样本丢弃分支；原厂后续按两个 FIFO 的头索引取位置/CV，再进行速度过滤。'],
        'unverified':[
            'AFSYNC 引脚边沿与传感器有效曝光窗口/FPGA统计帧的物理相位。',
            '两端时钟映射、镜头取位延迟、统计就绪延迟及实际镜头固件。',
            '原厂 FIFO 配对不能单独证明同帧或断流后重新对齐；接收时刻不能直接当曝光/取位时刻。',
            'FPGA 两通道的图像核与模糊模型代理不同，尚不能据代理试验启用同帧辅助标志。'],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'evidence.asm').write_text('\n\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('farmSha256','lensTableInitialTemplate','callbackThumb','verifiedStaticFacts','unverified')},ensure_ascii=False))

if __name__=='__main__':main()
