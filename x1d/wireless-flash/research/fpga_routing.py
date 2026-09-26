"""按固定数据库恢复局部布线与 CLB 配置；不等于完整网表或时序仿真。

仅处理调用方提供的内存数据。可变 PIP 目前限 INT_L/INT_R；其他类型
仅沿数据库的固定连接。未覆盖的资源作为边界，不能当作不连通的证明。
"""

from collections import defaultdict, deque
import json
import re


class Routing:
    def __init__(self, frames, grid, connections, dbfiles):
        self.frames, self.grid = frames, grid
        self.locations = {(v["grid_x"], v["grid_y"]): name for name, v in grid.items()}
        self.links = defaultdict(list)
        for item in connections:
            left, right = item["tile_types"]
            dx, dy = item["grid_deltas"]
            for wa, wb in item["wire_pairs"]:
                self.links[left, wa].append((dx, dy, right, wb))
                self.links[right, wb].append((-dx, -dy, left, wa))
        self.fixed, self.fixed_back = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
        self.defaults = defaultdict(dict)
        self.segbits, self.tile_types = {}, {}
        for name, data in dbfiles.items():
            if name.startswith("ppips_"):
                for line in data.decode("ascii").splitlines():
                    feature, mode = line.split()
                    kind, dest, src = feature.split(".")
                    if mode == "always":
                        self.fixed[kind][src].append(dest)
                        self.fixed_back[kind][dest].append(src)
                    elif mode == "default":
                        self.defaults[kind][dest] = src
                    elif mode != "hint":
                        raise ValueError("未知 ppips 模式")
            elif name.startswith("segbits_") and name.endswith(".db"):
                features = {}
                for line in data.decode("ascii").splitlines():
                    fields = line.split()
                    if not fields:
                        continue
                    entries = []
                    for term in fields[1:]:
                        frame, bit = map(int, term.lstrip("!").split("_"))
                        entries.append((frame, bit, not term.startswith("!")))
                    features[fields[0].split(".", 1)[1]] = entries
                self.segbits[name[8:-3].upper()] = features
            elif name.startswith("tile_type_") and name.endswith(".json"):
                self.tile_types[name[10:-5]] = json.loads(data)
        self.pin_lookup, self.site_meta = {}, {}
        for kind, doc in self.tile_types.items():
            if not kind.startswith("CLB"):
                continue
            lookup, sites = {}, {}
            for site in doc["sites"]:
                slot = int(re.search(r"X(\d+)", site["name"]).group(1))
                sites[slot] = site
                for pin, meta in site["site_pins"].items():
                    if meta and meta.get("wire"):
                        lookup[meta["wire"]] = (slot, site["type"], pin)
            self.pin_lookup[kind], self.site_meta[kind] = lookup, sites
        self.ps_ports = json.loads(dbfiles["ps7_ports.json"])
        self.ps_seeds = {}
        tiles_by_type = defaultdict(list)
        for name, tile in grid.items():
            tiles_by_type[tile["type"]].append(name)
        for kind, sources in self.fixed.items():
            if not kind.startswith("PSS") or len(tiles_by_type[kind]) != 1:
                continue
            for src, dests in sources.items():
                for wire in [src] + dests:
                    if wire.startswith("PS7_"):
                        self.ps_seeds[wire] = (tiles_by_type[kind][0], wire)
        self.selected, self.selected_back = {}, {}
        self.ambiguities, self.active_features = {}, {}

    def segment_values(self, name):
        segment = self.grid[name]["bits"]["CLB_IO_CLK"]
        base, off = int(segment["baseaddr"], 16), segment["offset"] * 4
        count = segment["words"] * 4
        return [int.from_bytes(self.frames[base + f][off:off + count], "little")
                for f in range(segment["frames"])]

    def features(self, name):
        if name not in self.active_features:
            kind = self.grid[name]["type"]
            values = self.segment_values(name)
            self.active_features[name] = [feature for feature, entries in self.segbits[kind].items()
                if all(bool(values[f] & (1 << bit)) == value for f, bit, value in entries)]
        return self.active_features[name]

    def pips(self, name):
        if name in self.selected:
            return self.selected[name], self.selected_back[name]
        kind = self.grid[name]["type"]
        forward, back = defaultdict(list), defaultdict(list)
        if kind in ("INT_L", "INT_R"):
            for feature in self.features(name):
                dest, src = feature.split(".")
                forward[src].append(dest)
                back[dest].append(src)
            ambiguity = {dest: sources for dest, sources in back.items() if len(sources) > 1}
            if ambiguity:
                self.ambiguities[name] = ambiguity
            for dest, src in self.defaults[kind].items():
                if not back.get(dest):
                    forward[src].append(dest)
                    back[dest].append(src)
        self.selected[name], self.selected_back[name] = forward, back
        return forward, back

    def neighbors(self, node, backwards=False):
        name, wire = node
        tile = self.grid[name]
        kind = tile["type"]
        for dx, dy, other_kind, other_wire in self.links.get((kind, wire), ()):
            other = self.locations.get((tile["grid_x"] + dx, tile["grid_y"] + dy))
            if other and self.grid[other]["type"] == other_kind:
                yield other, other_wire
        fixed = self.fixed_back if backwards else self.fixed
        for other_wire in fixed[kind].get(wire, ()):
            yield name, other_wire
        forward, back = self.pips(name)
        for other_wire in (back if backwards else forward).get(wire, ()):
            yield name, other_wire

    def trace(self, seed, backwards=False, limit=40000):
        if seed[0] not in self.grid:
            raise ValueError("起点 tile 不存在")
        parents, queue = {seed: None}, deque([seed])
        while queue:
            node = queue.popleft()
            for other in self.neighbors(node, backwards):
                if other not in parents:
                    parents[other] = node
                    queue.append(other)
                    if len(parents) > limit:
                        raise ValueError("布线遍历超过本次上限")
        return set(parents), parents

    def clb_pin(self, node):
        kind = self.grid[node[0]]["type"]
        if not kind.startswith("CLB"):
            return None
        return self.pin_lookup.get(kind, {}).get(node[1])

    def pin_wire(self, name, slot, pin):
        return name, self.site_meta[self.grid[name]["type"]][slot]["site_pins"][pin]["wire"]

    def prefix(self, name, slot):
        return self.site_meta[self.grid[name]["type"]][slot]["type"] + "_X" + str(slot)

    def drivers(self, node):
        seen, parents = self.trace(node, backwards=True)
        found = []
        for other in seen:
            pin = self.clb_pin(other)
            if pin and re.fullmatch(r"[ABCD](Q|MUX)?", pin[2]):
                found.append(other)
            elif other[1].startswith("PS7_"):
                port = re.sub(r"\d+$", "", other[1][4:])
                if self.ps_ports.get(port, {}).get("direction") == "output":
                    found.append(other)
            elif other[1] in ("VCC_WIRE", "GND_WIRE"):
                found.append(other)
        return sorted(found), seen, parents

    def input_sinks(self, nodes):
        return sorted(n for n in nodes if self.clb_pin(n)
                      and re.fullmatch(r"[ABCD][1-6X]", self.clb_pin(n)[2]))

    def lut(self, name, slot, letter):
        prefix = self.prefix(name, slot)
        active = self.features(name)
        init_prefix = prefix + "." + letter + "LUT.INIT["
        init = sum(1 << int(re.search(r"\[(\d+)\]", f).group(1))
                   for f in active if f.startswith(init_prefix))
        return {"prefix": prefix, "init": init,
                "inputs": {bit: self.drivers(self.pin_wire(name, slot, letter + str(bit)))[0]
                           for bit in range(1, 7)},
                "config": [f for f in active if f.startswith(prefix + ".") and ".INIT[" not in f]}

    def output(self, node):
        """局部输出选择；未覆盖的 carry/F7/F8 等保持 unknown，不猜测。"""
        pin = self.clb_pin(node)
        if not pin:
            return {"kind": "boundary", "node": node}
        slot, _, name = pin
        letter = name[0]
        active = self.features(node[0])
        prefix = self.prefix(node[0], slot)
        if name == letter:
            return {"kind": "lut", "slot": slot, "letter": letter, "width": 6}
        if name == letter + "Q":
            marker, ff = prefix + "." + letter + "FFMUX.", True
        elif name == letter + "MUX":
            marker, ff = prefix + "." + letter + "OUTMUX.", False
        else:
            return {"kind": "input", "node": node}
        selections = [f[len(marker):] for f in active if f.startswith(marker)]
        if len(selections) != 1:
            return {"kind": "unknown", "reason": "没有唯一输出选择", "selections": selections}
        selection = selections[0]
        if selection == letter + "5Q":
            ff = True
            mux = prefix + "." + letter + "5FFMUX."
            modes = [f[len(mux):] for f in active if f.startswith(mux)]
            selection = "O5" if modes == ["IN_A"] else letter + "X" if modes == ["IN_B"] else "unknown"
        if selection in ("O5", "O6"):
            return {"kind": "ff_lut" if ff else "lut", "slot": slot, "letter": letter,
                    "width": int(selection[-1])}
        if selection == letter + "X":
            return {"kind": "ff_pin" if ff else "pin", "slot": slot, "letter": letter,
                    "input": self.pin_wire(node[0], slot, letter + "X")}
        return {"kind": "unknown", "selection": selection, "ff": ff, "slot": slot, "letter": letter}
