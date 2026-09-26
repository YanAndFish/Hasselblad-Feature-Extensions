"""两个状态到独立 PL IRQ 的保守离线布线搜索；不输出可装机配置。

只允许使用 INT_L/INT_R 的数据库 PIP；原配置占用、原语引脚和未知资源
均阻止穿越。已接地的目标输入仅允许替换它自己的末级选择，不占用地线。
搜索结果必须经配置位重解及原网保持检查，不能仅凭路径视为完成。
"""
from collections import defaultdict, deque
from itertools import count
import hashlib
import heapq
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parents[1]
HOLD = ('CLBLL_R_X61Y68', 'CLBLL_LL_BQ')
IDLE = ('CLBLL_R_X61Y69', 'CLBLL_LL_DQ')
INVERTER_TILE = 'CLBLM_R_X19Y172'
INVERTER_SLOT = 1


class CandidateRouter:
    def __init__(self, route):
        self.route = route
        self.comp = {}
        self.members = []
        self.blocked = {}
        self.reasons = {}
        self.reserved = set()
        self.forward = {}
        self.back = {}
        for kind in ('INT_L', 'INT_R'):
            forward, back = defaultdict(list), defaultdict(list)
            for feature in route.segbits[kind]:
                dest, src = feature.split('.')
                forward[src].append((dest, feature))
                back[dest].append((src, feature))
            self.forward[kind], self.back[kind] = forward, back

    def static_neighbors(self, node, both=False, backwards=False):
        name, wire = node
        tile = self.route.grid[name]
        kind = tile['type']
        for dx, dy, other_kind, other_wire in self.route.links.get((kind, wire), ()):
            other = self.route.locations.get((tile['grid_x']+dx, tile['grid_y']+dy))
            if other and self.route.grid[other]['type'] == other_kind:
                yield other, other_wire
        maps = (self.route.fixed, self.route.fixed_back) if both else (
            self.route.fixed_back if backwards else self.route.fixed,)
        for links in maps:
            for other in links[kind].get(wire, ()):
                yield name, other

    def component(self, node):
        if node in self.comp:
            return self.comp[node]
        found, todo = {node}, [node]
        while todo:
            for other in self.static_neighbors(todo.pop(), both=True):
                if other not in found:
                    if len(found) >= 20000:
                        raise ValueError('固定网络过大，拒绝当作空闲布线')
                    found.add(other)
                    todo.append(other)
        index = len(self.members)
        for item in found:
            if item in self.comp:
                raise RuntimeError('静态连通分量出现不一致')
            self.comp[item] = index
        self.members.append(found)
        return index

    def occupied(self, index):
        if index in self.reserved:
            return True
        if index not in self.blocked:
            reasons = []
            for name, wire in self.members[index]:
                kind = self.route.grid[name]['type']
                # 未启用的原语输出也不是可借用的布线资源。
                pin = self.route.clb_pin((name, wire))
                passthrough = re.search(r'(?:^|_)(?:[NSEW]{2}[246]|[NSEW][LR]1)(?:BEG|END|MID|[ABE])', wire)
                primitive = pin is not None or wire.startswith('PS7_')
                if not kind.startswith('INT_') and not kind.startswith('CLB') and not passthrough:
                    primitive = True
                if primitive:
                    reasons.append(('primitive', name, wire))
                    break
                forward, back = self.route.pips(name)
                if forward.get(wire) or back.get(wire):
                    reasons.append(('configured-pip', name, wire))
                    break
                if wire in ('GND_WIRE', 'VCC_WIRE'):
                    reasons.append(('constant', name, wire))
                    break
            self.blocked[index] = bool(reasons)
            self.reasons[index] = reasons
        return self.blocked[index]

    def find(self, source, target, limit=250000):
        source_nodes, _ = self.route.trace(source)
        target_component = self.component(target)
        start_components = {self.component(n) for n in source_nodes}
        if target_component in start_components:
            raise ValueError('源和目标已经相连，拒绝重复构造')
        target_members = self.members[target_component]
        # 终点只能是一个 PIP 可替换的独立输入；不允许改动多个选择端。
        replacements = []
        for name, wire in target_members:
            kind = self.route.grid[name]['type']
            if kind in self.back:
                for old in self.route.features(name):
                    if old.split('.')[0] == wire:
                        replacements.append((name, old))
        if len(replacements) > 1:
            raise ValueError('目标没有唯一可替换的末级 PIP: '+repr(replacements))
        if not replacements:
            defaults = [(name, wire, self.route.defaults[self.route.grid[name]['type']][wire])
                        for name, wire in target_members
                        if wire in self.route.defaults[self.route.grid[name]['type']]]
            if len(defaults) != 1:
                raise ValueError('未配置目标没有唯一默认输入: '+repr(defaults))
        dest_tile = self.route.grid[target[0]]
        serial, heap, costs, parents = count(), [], {}, {}
        for node in sorted(source_nodes):
            costs[node] = 0
            parents[node] = None
            heapq.heappush(heap, (0, 0, next(serial), node))
        visited = 0
        reached = None
        while heap:
            _, cost, _, node = heapq.heappop(heap)
            if costs.get(node) != cost:
                continue
            visited += 1
            if visited > limit:
                break
            if node == target:
                reached = node
                break
            options = [(other, None, 0) for other in self.static_neighbors(node)]
            name, wire = node
            kind = self.route.grid[name]['type']
            options.extend(((name, dest), (name, feature), 1)
                           for dest, feature in self.forward.get(kind, {}).get(wire, ()))
            for other, feature, increment in options:
                comp = self.component(other)
                if comp not in start_components and comp != target_component and self.occupied(comp):
                    continue
                if feature and comp in start_components:
                    continue
                new_cost = cost + increment
                if new_cost >= costs.get(other, 1 << 30):
                    continue
                costs[other], parents[other] = new_cost, (node, feature)
                tile = self.route.grid[other[0]]
                distance = abs(tile['grid_x']-dest_tile['grid_x'])+abs(tile['grid_y']-dest_tile['grid_y'])
                # 加权引导只决定尝试顺序，不宣称得到最短路或时序最优路。
                heapq.heappush(heap, (new_cost+distance/2, new_cost, next(serial), other))
        self.last_costs = costs
        if reached is None:
            return {'found': False, 'source': source, 'target': target,
                    'visited': visited, 'pending': len(heap), 'capped': bool(heap),
                    'knownComponents': len(self.members), 'replacement': replacements}
        path, pips = [], []
        while reached is not None:
            path.append(reached)
            parent = parents[reached]
            if parent is None:
                break
            previous, feature = parent
            if feature:
                pips.append(feature)
            reached = previous
        path.reverse()
        pips.reverse()
        return {'found': True, 'source': source, 'target': target, 'path': path,
                'addPips': pips, 'removePips': replacements, 'visited': visited,
                'knownComponents': len(self.members), 'capped': False,
                'physicalTimingValidated': False, 'configurationBitsRechecked': False}


def run(route):
    router = CandidateRouter(route)
    target = ('PSS2_X32Y157', 'PS7_IRQF2P14')
    prefix = route.prefix(INVERTER_TILE, INVERTER_SLOT)
    # 整个 slice 只有原厂默认时钟/进位选择；拒绝借用已使用的 LUT、FF 或进位逻辑。
    active = [f for f in route.features(INVERTER_TILE) if f.startswith(prefix+'.')]
    if set(active) != {prefix+'.NOCLKINV', prefix+'.PRECYINIT.C0'}:
        raise ValueError('候选反相器 slice 已被使用或基线改变')
    inverter_input = route.pin_wire(INVERTER_TILE, INVERTER_SLOT, 'A1')
    inverter_output = route.pin_wire(INVERTER_TILE, INVERTER_SLOT, 'A')
    nodes, _ = route.trace(inverter_output)
    if len(nodes) != 3 or route.input_sinks(nodes):
        raise ValueError('反相器输出已有其他用途')
    requests = [('start_hold', HOLD, target), ('idle_input', IDLE, inverter_input),
                ('exit_idle', inverter_output, ('PSS2_X32Y157', 'PS7_IRQF2P15'))]
    routes = []
    for name, source, destination in requests:
        row = router.find(source, destination)
        row['name'] = name
        routes.append(row)
        if not row['found']:
            break
        router.reserved.update(router.component(n) for n in row['path'])
    result = {'found': len(routes) == 3 and all(r['found'] for r in routes), 'routes': routes,
              'inverter': {'tile': INVERTER_TILE, 'slot': INVERTER_SLOT, 'letter': 'A',
                  'input': inverter_input, 'output': inverter_output, 'init': 0x5555555555555555,
                  'baselineSliceFeatures': active},
              'hardwareRequests': 0, 'installed': False, 'newInterruptImplemented': False,
              'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (HERE/'research/mechanical-irq-route.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return router, result


if __name__ == '__main__':
    from mechanical_fpga_route import load
    route, _, _ = load()
    _, result = run(route)
    print({k: v for k, v in result.items() if k not in ('path', 'addPips')})
