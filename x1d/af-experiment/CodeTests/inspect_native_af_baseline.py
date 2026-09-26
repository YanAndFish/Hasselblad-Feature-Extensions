"""固定X1D 1.25.0 FARM原厂AF证据导出；完全离线，不导入硬件模块。"""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication

REGIONS=(
    ('cv_interrupt_producer',0x1986d8,0x198778),
    ('cv_fpga_ready_and_channels',0x1f0c20,0x1f0e6c),
    ('native_contrast_floor',0x199b50,0x199c70),
    ('native_fine_speed_selection',0x1a3e08,0x1a3eb4),
    ('direction_state3',0x19d19c,0x19d5c8),
    ('past_peak_state4',0x19d5c8,0x19d87c),
    ('original_peak_fit_and_reverse',0x19d87c,0x19d9cc),
    ('three_point_direction_metric',0x19e47c,0x19e7f0),
    ('native_speed_command',0x1a0240,0x1a0378),
    ('cv_fifo',0x1a1a98,0x1a1cd4),
    ('position_fifo_and_velocity',0x1a1cd8,0x1a22bc),
    ('segment_direction_hint',0x1a2884,0x1a2a30),
    ('fifo_pairing_and_speed_filter',0x1a2a30,0x1a3168),
    ('direction_statistical_filter',0x1a3a6c,0x1a3d80),
    ('native_cycle_reset',0x1a4950,0x1a4af0),
)

def main():
    farm=FarmApplication()
    assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    output=HERE/'build/native-af-r1'
    output.mkdir(parents=True,exist_ok=True)
    regions=[];sections=[]
    for name,start,end in REGIONS:
        blob=farm.read(start,end-start)
        regions.append({'name':name,'start':hex(start),'endExclusive':hex(end),'sha256':hashlib.sha256(blob).hexdigest()})
        sections.append(f'; {name} {start:#x}..{end:#x}\n'+farm.disassembly(start,end-start))
    constants={}
    for address in (0x2adc2c,0x2adc30,0x2adc3c,0x2adc68,0x2adc6c,0x2adc70,0x2adc74):
        value=farm.word(address)
        constants[hex(address)]={'word':hex(value),'float32Interpretation':struct.unpack('<f',struct.pack('<I',value))[0]}
    report={'baselineSha256':farm.sha256,'scope':'原厂固定固件静态证据，不代表当前相机运行状态',
            'hardwareRequests':0,'regions':regions,'imageConstantsNotLiveParameters':constants,
            'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'native-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'native-evidence.asm').write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
