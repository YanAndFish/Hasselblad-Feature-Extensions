"""传感器启动与模式位的有界局部逻辑扇出；保留所有越界和未解析资源。"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDS = [('CLBLM_R_X59Y68', 'CLBLM_L_BQ'),
         ('CLBLM_R_X59Y68', 'CLBLM_L_CQ'),
         ('CLBLM_R_X59Y68', 'CLBLM_L_CMUX')]


def analyze(route, logic):
    refs_cache = {}
    boundaries = {}
    def refs(root):
        if root in refs_cache:
            return refs_cache[root]
        first = logic.cell(root)
        todo = [first[k] for k in ('d', 'ce', 'sr')] if first['op'] == 'ff' else [root]
        seen = set()
        while todo:
            node = todo.pop()
            if isinstance(node, int) or node in seen:
                continue
            seen.add(node)
            if len(seen) > 4000:
                raise ValueError('单个组合锥超限')
            cell = logic.cell(node)
            if cell['op'] == 'alias':
                todo.append(cell['input'])
            elif cell['op'] in ('table', 'mux', 'xor'):
                todo.extend(cell['inputs'])
            elif cell['op'] == 'boundary':
                boundaries[node] = cell['reason']
        refs_cache[root] = seen
        return seen
    pending, seen, edges, outside, outputs = list(SEEDS), set(), [], set(), set()
    while pending:
        source = pending.pop()
        if source in seen:
            continue
        seen.add(source)
        if len(seen) > 1200:
            raise ValueError('局部逻辑扇出超限，不能当作完整覆盖')
        net, _ = route.trace(source)
        outputs.update(n for n in net if n[0].startswith('RIOB') and re.fullmatch(r'IOB_O[01]', n[1]))
        slots = {(n[0], route.clb_pin(n)[0]) for n in net if route.clb_pin(n)
                 and (re.fullmatch(r'[ABCD][1-6X]', route.clb_pin(n)[2]) or route.clb_pin(n)[2] in ('CE', 'SR', 'CIN'))}
        for tile, slot in slots:
            xy = re.search(r'_X(\d+)Y(\d+)$', tile)
            if not (40 <= int(xy[1]) <= 79 and 40 <= int(xy[2]) <= 100):
                outside.add((tile, slot))
                continue
            available = route.site_meta[route.grid[tile]['type']][slot]['site_pins']
            for pin in ('A', 'B', 'C', 'D', 'AQ', 'BQ', 'CQ', 'DQ', 'AMUX', 'BMUX', 'CMUX', 'DMUX', 'COUT'):
                if pin not in available:
                    continue
                target = route.pin_wire(tile, slot, pin)
                if source == target or source not in refs(target):
                    continue
                edges.append((source, target))
                if target not in seen:
                    pending.append(target)
    return {'status': '有界结构依赖扫描；不是运行时可达性或物理时序证明',
            'hardware_requests': 0, 'seeds': SEEDS, 'region': 'CLB X40..79 / Y40..100',
            'logic_nodes': sorted(seen), 'edges': edges, 'output_data_terminals': sorted(outputs),
            'outside_region_slots': sorted(outside),
            'unresolved_resources': [{'node': n, 'reason': r} for n, r in boundaries.items()],
            'limitations': ['组合或状态依赖并不证明当前配置一定激活该路径',
                            '所有范围外逻辑均列出，未宣称全芯片输出穷尽',
                            '输出数据端连通不代表板级用途或电气输出使能已验证']}


if __name__ == '__main__':
    from mechanical_fpga_route import load
    route, logic, metadata = load()
    result = analyze(route, logic)
    (HERE / 'mechanical-sensor-fanout.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('logic_nodes', len(result['logic_nodes']), 'outputs', result['output_data_terminals'],
          'outside', len(result['outside_region_slots']), 'unresolved', len(result['unresolved_resources']))
