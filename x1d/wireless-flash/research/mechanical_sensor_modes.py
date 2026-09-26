"""复用已保存的传感器局部模型，比较模式和外部启动条件；无设备访问。"""
import copy
import hashlib
import json
from pathlib import Path

from fpga_cycle_model import Snapshot, freeze, run_explicit_case

HERE = Path(__file__).resolve().parent


def prepare(cycles=1600, controls=(1, 2, 3, 0x101, 0x102, 0x103, 0x201, 0x202, 0x203, 0x301, 0x302, 0x303), waveforms=('zero', 'rise100', 'fall100')):
    raw = (HERE / 'fpga-sensorif-netlist.json').read_bytes()
    replay = json.loads((HERE / 'fpga-sensorif-replay.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(raw).hexdigest() == replay['model_sha256']
    snapshot = Snapshot(json.loads(raw))
    evidence = json.loads((HERE / 'fpga-sensorif-evidence.json').read_text(encoding='utf-8'))
    mode_nodes = [freeze(n) for n in evidence['mode_registers']]
    data_nodes = {int(k.removeprefix('PS7_MAXIGP0WDATA')): freeze(v)
                  for k, v in evidence['write_data_captures'].items()}
    external = ('unresolved', 'CLBLL_R_X61Y68', 'CLBLL_LL_C6')
    probes = [
        ('CLBLL_R_X61Y68', 'CLBLL_LL_BQ'),
        ('CLBLM_R_X63Y72', 'CLBLM_L_BQ'),
        ('CLBLM_R_X71Y65', 'CLBLM_L_AQ'),
        ('CLBLM_R_X71Y65', 'CLBLM_L_BQ'),
        ('CLBLL_R_X61Y68', 'CLBLL_LL_DMUX'),
    ]
    assert all(n in snapshot.indices for n in probes)
    cases = []
    for mode in range(4):
        for control in controls:
            for waveform in waveforms:
                case = copy.deepcopy(replay['cases'][-1])
                case['name'] = f'mode{mode}_control{control:x}_{waveform}'
                case['cycles'] = cycles
                case['probes'] = probes
                replacements = {node: (mode >> bit) & 1 for bit, node in enumerate(mode_nodes)}
                replacements.update({node: (control >> bit) & 1 for bit, node in data_nodes.items()})
                replacements[external] = int(waveform == 'fall100')
                def replace(values):
                    return [[node, replacements.get(freeze(node), value)] for node, value in values]
                case['initial_boundary_values'] = replace(case['initial_boundary_values'])
                for update in case['boundary_updates']:
                    update['values'] = replace(update['values'])
                if waveform != 'zero':
                    case['boundary_updates'].append({'cycle': 100, 'values': [[external, int(waveform == 'rise100')]]})
                case.update(mode=mode, control=control, waveform=waveform)
                cases.append(case)
    metadata = {'status': '离线合成条件比较，不代表机械模式实际配置或物理积分时刻',
            'model_sha256': hashlib.sha256(raw).hexdigest(), 'hardware_requests': 0,
            'baseline': 'fpga-sensorif-replay.json 最后一例，H512/V64；启动请求仍为周期10',
            'cycles_per_case': cycles, 'probes': probes,
            'limitations': ['外部输入为显式合成波形，未核对板级用途',
                            '未模拟 AXI 事务或传感器内部积分',
                            '模式0至3均枚举，不将某个模式预先称为机械模式',
                            '复用固定历史局部快照，未将最新布线扩展静默混入模型']}
    return snapshot, cases, metadata


def analyze():
    snapshot, cases, metadata = prepare()
    results = []
    for case in cases:
        events, final = run_explicit_case(snapshot, case)
        results.append({key: case[key] for key in ('name', 'mode', 'control', 'waveform')} |
                       {'events': events, 'final_probes': [final[snapshot.indices[n]] for n in case['probes']]})
    return metadata | {'cases': results}


if __name__ == '__main__':
    result = analyze()
    (HERE / 'mechanical-sensor-modes.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('cases', len(result['cases']), 'hardware_requests', result['hardware_requests'])
    for item in result['cases']:
        if item['mode'] == 3 and item['control'] & 3 == 2:
            print(item['name'], item['events'][:8])
