"""离线核对固定 FPGA 的全部 IRQF2P 直接输入，明确不等于全逻辑可达性分析。"""
from pathlib import Path
import hashlib
import json
import sys
sys.dont_write_bytecode=True
from mechanical_fpga_route import load

HERE=Path(__file__).resolve().parents[1]

def analyze():
    route,logic,metadata=load()
    rows=[]
    for number in range(20):
        node=('PSS2_X32Y157','PS7_IRQF2P'+str(number))
        drivers,nodes,_=route.drivers(node)
        if len(drivers)!=1: raise RuntimeError('IRQ input has no unique decoded driver')
        rows.append({'input':number,'interruptClass':'SPI' if number<16 else 'CPU nIRQ/nFIQ PPI',
                     'gicId':(61+number if number<8 else 84+number-8) if number<16 else None,
                     'pin':node,'driver':drivers[0],'nodes':len(nodes),
                     'constantLow':drivers[0][1]=='GND_WIRE'})
    idle=route.pin_wire('CLBLL_R_X61Y69',0,'DQ')
    nodes,_=route.trace(idle)
    reached=sorted(n for n in nodes if 'IRQF2P' in n[1])
    assert [r['input'] for r in rows if r['constantLow']]==[5,14,15,16,17,18,19]
    assert rows[12]['driver']==('CLBLM_R_X11Y67','CLBLM_M_C')
    report={'source':'X1D 1.25.0 official FPGA configuration',
            'fpgaSha256':'8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30',
            'irqInputs':rows,'idleBitDriver':idle,'idleDirectNetNodes':len(nodes),
            'idleDirectIrqPins':reached,'allLogicalDependenciesScanned':False,
            'newHardwareInterruptImplemented':False,'hardwareRequests':0,
            'limitation':'只覆盖已解码配置中的直接布线。接地输入不是已获准占用的空闲资源；不证明没有经其他逻辑的间接联系。',
            'sourceHash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output=HERE/'research/mechanical-irq-inventory.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'inputs':len(rows),'constantLowInputs':[r['input'] for r in rows if r['constantLow']],
            'idleDirectIrqPins':reached,'hardwareRequests':0}

if __name__=='__main__': print(analyze())
