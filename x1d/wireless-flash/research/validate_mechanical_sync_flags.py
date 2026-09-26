"""普通启动控制 3/7 的 A/B 保持位清除对照；仅固定 FPGA 桌面模型。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fpga_cycle_model import Snapshot, freeze
from fpga_sticky_sync import compare_cases
from mechanical_sensor_modes import prepare

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / 'build/mechanical-sync-capture'


def run():
    assert Path.cwd().resolve() == HERE.parents[1]
    original_path = HERE / 'research/fpga-sensorif-netlist.json'
    extended_path = HERE / 'build/farm-sync-capture/fpga-sync-netlist.json'
    original = json.loads(original_path.read_text(encoding='utf-8'))
    extended = json.loads(extended_path.read_text(encoding='utf-8'))
    snapshot = Snapshot(extended)
    evidence = json.loads((HERE / 'research/fpga-sensorif-evidence.json').read_text(encoding='utf-8'))
    data = {bit: freeze(evidence['write_data_captures']['PS7_MAXIGP0WDATA' + str(bit)]) for bit in (0, 1, 2, 6)}
    probes = [('CLBLM_R_X63Y66', 'CLBLM_M_AQ'),
              ('CLBLM_R_X65Y69', 'CLBLM_M_AQ'),
              ('CLBLM_R_X63Y69', 'CLBLM_L_BQ'),
              ('CLBLL_R_X61Y68', 'CLBLL_LL_BQ'),
              ('CLBLM_R_X71Y65', 'CLBLM_L_AQ'),
              ('CLBLM_R_X71Y65', 'CLBLM_L_BQ')]
    _, cases, _ = prepare(cycles=1600, controls=(3, 7), waveforms=('zero',))
    results = []
    for source in cases:
        pair = []
        for clear in (0, 1):
            case = deepcopy(source)
            case['name'] += '_clear' if clear else '_original'
            case['initial_boundary_values'].append([data[6], 0])
            added = []
            for cycle, source_cycle in ((6, 10), (7, 11)):
                values = {freeze(n): v for n, v in next(u['values'] for u in case['boundary_updates'] if u['cycle'] == source_cycle)}
                values.update({data[0]: 0, data[1]: 0, data[2]: 0, data[6]: clear})
                added.append({'cycle': cycle, 'values': list(values.items())})
            for update in case['boundary_updates']:
                update['values'].append([data[6], 0])
            case['boundary_updates'] = sorted(case['boundary_updates'] + added, key=lambda u: u['cycle'])
            pair.append(case)
        result = compare_cases(snapshot, [e['node'] for e in original['state_cells']], pair[0], pair[1], probes)
        events = result['candidateEvents']
        assert result['originalStatesIdentical']
        assert any(6 <= tick < 10 and values[1:3] == (0, 0) for tick, values in events)
        assert any(tick > 10 and values[1:3] == (1, 1) for tick, values in events)
        result.update(mode=source['mode'], control=source['control'], passed=True)
        results.append(result)
    fanout = json.loads((HERE / 'build/farm-sync-capture/fpga-clear-fanout.json').read_text(encoding='utf-8'))
    assert fanout['coveredGraphExhausted'] and not fanout['original_state_intersection']
    assert not any(e['special'] for e in fanout['nodes'])
    report = {'passed': True, 'hardware_requests': 0, 'physical_timing_measured': False,
              'scope': 'opmode 0..3、控制 3/7、H512/V64 的局部清除对照，非真实 AXI 或板级测量',
              'probe_names': ['clear', 'B_sticky', 'A_sticky', 'start_hold', 'A_output', 'B_output'],
              'cases': results, 'source_hashes': {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (original_path, extended_path, Path(__file__))}}
    OUT.mkdir(exist_ok=True)
    (OUT / 'fpga-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'passed': True, 'cases': len(results), 'hardware_requests': 0}
