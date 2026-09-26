"""传感器外部启动输入至预闪中断的离线布线、门控及采样复核。"""
import json
from pathlib import Path

from fpga_cycle_model import compile_half_step
from mechanical_fpga_route import load

HERE = Path(__file__).resolve().parent
INPUT = ('unresolved', 'CLBLM_R_X19Y65', 'CLBLM_M_A3')
RESET = ('CLBLM_R_X19Y167', 'CLBLM_L_CQ')
ROOT = ('CLBLM_R_X11Y67', 'CLBLM_M_C')
IO = ('RIOI_SING_X79Y50', 'IOI_ILOGIC0_O')
IRQ = ('PSS2_X32Y157', 'PS7_IRQF2P12')
CLOCK = ('CLK_HROW_BOT_R_X102Y78', 'CLK_HROW_CK_HCLK_OUT_L2')


def analyze(route, logic):
    input_nodes, _ = route.trace(IO)
    assert ('CLBLL_R_X61Y68', 'CLBLL_LL_C6') in input_nodes
    assert ('CLBLM_R_X19Y65', 'CLBLM_M_A3') in input_nodes
    irq_nodes, _ = route.trace(ROOT)
    assert IRQ in irq_nodes and route.drivers(IRQ)[0] == [ROOT]
    assert logic.cell(ROOT)['input'] == ('lut', 'CLBLM_R_X11Y67', 0, 'C', 6)
    gate = logic.cell(('lut', 'CLBLM_R_X11Y67', 0, 'C', 6))
    assert gate['truth'] == 8 and len(gate['inputs']) == 2
    states, cells, boundaries = {}, {}, {INPUT, RESET}
    todo, seen = [ROOT], set()
    while todo:
        node = todo.pop()
        if node in seen or isinstance(node, int) or node in boundaries:
            continue
        seen.add(node)
        if len(seen) > 1000:
            raise ValueError('组合锥超限，不得当作完成')
        cell = logic.cell(node)
        cells[node] = cell
        if cell['op'] == 'ff':
            states[node] = cell
            todo.extend(cell[k] for k in ('d', 'ce', 'sr'))
        elif cell['op'] == 'alias':
            todo.append(cell['input'])
        elif cell['op'] in ('table', 'mux', 'xor'):
            todo.extend(cell['inputs'])
        elif cell['op'] == 'boundary':
            raise ValueError('出现额外未指定边界')
    assert len(states) == 18
    clocks = sorted({cell['clock_pin'] for cell in states.values()})
    assert all(CLOCK in route.trace(pin, backwards=True)[0] for pin in clocks)
    assert all(not cell['clock_inverted'] and not cell['latch'] for cell in states.values())
    indices = {n: i for i, n in enumerate(list(states) + sorted(boundaries))}
    step, source, _ = compile_half_step(logic, states, indices, False)
    results = []
    for width in (1, 4999, 5000, 5001, 5002, 5003, 6000, 44990):
        values = [states[n]['init'] if n in states else 0 for n in indices]
        previous, events = None, []
        for tick in range(width + 30):
            values[indices[INPUT]] = int(10 <= tick < 10 + width)
            values[indices[RESET]] = 0
            step(values)
            observed = logic.evaluate(ROOT, dict(zip(indices, values)))
            if observed != previous:
                events.append((tick, observed))
                previous = observed
        results.append({'input_high_from': 10, 'input_high_cycles': width,
                        'cycles': width + 30, 'reset': 0, 'irq_events': events})
    return {'status': '固定官方配置的结构联系与条件化局部模型；未实机验证',
            'hardware_requests': 0, 'fpga_sha256': '8df07fecb3ccb1227ea696a19b52622be124426cb493724eea1f5705c7245a30',
            'input_node': IO, 'input_fanout_nodes': sorted(input_nodes),
            'input_iob_features': route.features('RIOB18_SING_X79Y50'),
            'input_ioi_features': route.features('RIOI_SING_X79Y50'),
            'irq': IRQ, 'gic_id': 88, 'irq_nodes': sorted(irq_nodes),
            'irq_mapping_source': 'https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Interrupt-Signals',
            'clock_marker': CLOCK, 'clock_pins': clocks,
            'cells': [{'node': n, 'cell': c} for n, c in cells.items()],
            'explicit_boundaries': [INPUT, RESET], 'cases': results,
            'limitations': ['尚未确认外部输入的板级信号名称和普通机械拍摄覆盖',
                            '两条采样支路时钟标记不同，不把模型周期直接互换或换算物理时间',
                            '中断服务属于预闪，不能据此称为主闪事件',
                            '保持原厂门控；没有修改、订阅或导出中断']}


if __name__ == '__main__':
    route, logic, metadata = load()
    result = analyze(route, logic)
    (HERE / 'mechanical-sensor-irq.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('输入双扇出和中断路由验证通过；局部触发器18；硬件请求0')
    for case in result['cases']:
        print(case['input_high_cycles'], case['irq_events'])
