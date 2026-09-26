"""离线核对拍摄中重新清同步保持位；不装载、不访问相机。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from fpga_cycle_model import Snapshot, freeze
from fpga_sticky_sync import compare_cases

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/farm-sync-capture'


def run(clear_cycle=4000):
    if clear_cycle not in (20,4000):
        raise ValueError('仅接受本轮两个显式检查点')
    read=lambda path: json.loads(path.read_text(encoding='utf-8'))
    original=read(HERE/'research/fpga-sensorif-netlist.json')
    snapshot=Snapshot(read(OUT/'fpga-sync-netlist.json'))
    baseline=read(OUT/'fpga-sync-cases.json')[0]['candidate']
    evidence=read(HERE/'research/fpga-sensorif-evidence.json')
    bits={i:freeze(evidence['write_data_captures']['PS7_MAXIGP0WDATA'+str(i)]) for i in (0,1,6)}
    start={freeze(n):v for n,v in next(u['values'] for u in baseline['boundary_updates'] if u['cycle']==10)}
    end={freeze(n):v for n,v in next(u['values'] for u in baseline['boundary_updates'] if u['cycle']==11)}
    probes=[('CLBLM_R_X63Y66','CLBLM_M_AQ'),('CLBLM_R_X65Y69','CLBLM_M_AQ'),
            ('CLBLM_R_X71Y65','CLBLM_L_BQ')]
    results=[]
    for command_bit in (0,1):
        candidate=deepcopy(baseline)
        candidate['name']='second_b_clear_command_bit_'+str(command_bit)
        # 20 在首脉冲内，4000 在其结束之后；均为合成模型周期。
        for cycle,request,clear in ((clear_cycle,start,1),(clear_cycle+1,end,1),
                                    (clear_cycle+4,start,0),(clear_cycle+5,end,0)):
            values=dict(request)
            values.update({bits[0]:command_bit,bits[1]:1,bits[6]:clear})
            candidate['boundary_updates'].append({'cycle':cycle,'values':list(values.items())})
        candidate['boundary_updates'].sort(key=lambda u:u['cycle'])
        result=compare_cases(snapshot,[e['node'] for e in original['state_cells']],baseline,candidate,probes)
        results.append(result)
        print(json.dumps({'commandBit':command_bit,'originalStatesIdentical':result['originalStatesIdentical'],
                          'firstMismatches':result['firstMismatches'],'events':result['candidateEvents'][:16]}),flush=True)
    report={'hardwareRequests':0,'installed':False,'physicalTimingMeasured':False,
            'scope':'局部合成模型；不证明完整总线写入或传感器电气行为',
            'clearCycle':clear_cycle,'releaseCycle':clear_cycle+4,
            'sourceHash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'inputHash':hashlib.sha256((OUT/'fpga-sync-netlist.json').read_bytes()).hexdigest(),
            'results':results}
    (OUT/('second-b-clear-review-'+str(clear_cycle)+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    run(20)
    run(4000)
