"""局部 CLB 逻辑模型。只解析调用方提供的离线布线；不是完整 FPGA 仿真。

支持普通 LUT、触发器数据选择、CARRY4、F7/F8。RAM/SRL、未覆盖资源、
未解布线保留为边界，不能默认为零。evaluate 不跨越触发器，也不产生时钟。
CE/SR 的实际选择与初始化值单独保留；未经时钟核对不得当作实机周期模型。
"""

import re


def reduced_table(inputs, truth):
    """只合并同一来源，消去常量和实际不参与输出的输入。"""
    keys = list(dict.fromkeys(i for i in inputs if not isinstance(i, int)))
    table = 0
    for row in range(1 << len(keys)):
        index = sum((ref if isinstance(ref, int) else (row >> keys.index(ref)) & 1) << bit
                    for bit, ref in enumerate(inputs))
        table |= ((truth >> index) & 1) << row
    used = [bit for bit in range(len(keys)) if any(
        ((table >> row) ^ (table >> (row ^ (1 << bit)))) & 1
        for row in range(1 << len(keys)))]
    result = 0
    for row in range(1 << len(used)):
        index = sum(((row >> bit) & 1) << old for bit, old in enumerate(used))
        result |= ((table >> index) & 1) << row
    return {"op": "table", "inputs": tuple(keys[i] for i in used), "truth": result}


class Logic:
    def __init__(self, routing):
        self.route = routing
        self.cells = {}
        self.sources = {}

    def source(self, pin):
        if pin not in self.sources:
            drivers, nodes, _ = self.route.drivers(pin)
            drivers = sorted(set(drivers) | {
                n for n in nodes if self.route.clb_pin(n)
                and self.route.clb_pin(n)[2] == "COUT"})
            if drivers and all(d[1] == "VCC_WIRE" for d in drivers):
                result = 1
            elif drivers and all(d[1] == "GND_WIRE" for d in drivers):
                result = 0
            elif len(drivers) == 1:
                result = drivers[0]
            elif not drivers:
                result = ("unresolved",) + pin
            else:
                raise ValueError("存在多个不同驱动，不能推定逻辑值: " + repr((pin, drivers)))
            self.sources[pin] = result
        return self.sources[pin]

    def site_features(self, name, slot):
        prefix = self.route.prefix(name, slot) + "."
        return {f[len(prefix):] for f in self.route.features(name) if f.startswith(prefix)}

    def pin_source(self, name, slot, pin):
        return self.source(self.route.pin_wire(name, slot, pin))

    def lut_cell(self, name, slot, letter, width):
        features = self.site_features(name, slot)
        if letter + "LUT.RAM" in features or letter + "LUT.SRL" in features:
            return {"op": "boundary", "reason": "RAM/SRL 不是静态 LUT"}
        prefix = letter + "LUT.INIT["
        init = sum(1 << int(re.search(r"\[(\d+)\]", f).group(1))
                   for f in features if f.startswith(prefix))
        inputs = [self.pin_source(name, slot, letter + str(i)) for i in range(1, width + 1)]
        result = reduced_table(inputs, init & ((1 << (1 << width)) - 1))
        result["raw_init"] = init
        return result

    def selected_data(self, name, slot, letter, selection):
        if selection in ("O5", "O6"):
            return ("lut", name, slot, letter, int(selection[1]))
        if selection == letter + "X":
            return self.pin_source(name, slot, letter + "X")
        if selection in ("XOR", "CY"):
            return ("xor" if selection == "XOR" else "co", name, slot, "ABCD".index(letter))
        if selection == "F7" and letter in "AC":
            return ("f7", name, slot, letter)
        if selection == "F8" and letter == "B":
            return ("f8", name, slot)
        return ("unsupported", name, slot, letter, selection)

    def ff_cell(self, name, slot, letter, ff5, data):
        fs = self.site_features(name, slot)
        tag = letter + ("5" if ff5 else "") + "FF"
        return {"op": "ff", "d": data,
                "ce": self.pin_source(name, slot, "CE") if "CEUSEDMUX" in fs else 1,
                "sr": self.pin_source(name, slot, "SR") if "SRUSEDMUX" in fs else 0,
                "clock_pin": self.route.pin_wire(name, slot, "CLK"),
                "clock_inverted": "CLKINV" in fs,
                "synchronous_sr": "FFSYNC" in fs,
                "latch": "LATCH" in fs and not ff5,
                "init": int(tag + ".ZINI" not in fs),
                "sr_value": int(tag + ".ZRST" not in fs)}

    def build_physical(self, node):
        pin = self.route.clb_pin(node)
        if not pin:
            return {"op": "boundary", "reason": "未覆盖的外部或专用资源"}
        slot, _, terminal = pin
        name = node[0]
        if terminal == "COUT":
            return {"op": "alias", "input": ("co", name, slot, 3)}
        if not re.fullmatch(r"[ABCD](Q|MUX)?", terminal):
            return {"op": "alias", "input": self.source(node)}
        letter = terminal[0]
        if terminal == letter:
            return {"op": "alias", "input": ("lut", name, slot, letter, 6)}
        fs = self.site_features(name, slot)
        is_ff = terminal.endswith("Q")
        marker = letter + ("FFMUX." if is_ff else "OUTMUX.")
        selections = [f[len(marker):] for f in fs if f.startswith(marker)]
        if len(selections) != 1:
            return {"op": "boundary", "reason": "没有唯一的输出选择"}
        selection = selections[0]
        ff5 = selection == letter + "5Q"
        if ff5:
            mux = letter + "5FFMUX."
            modes = [f[len(mux):] for f in fs if f.startswith(mux)]
            if modes not in (["IN_A"], ["IN_B"]):
                return {"op": "boundary", "reason": "没有唯一的 5FF 数据选择"}
            selection = "O5" if modes == ["IN_A"] else letter + "X"
        data = self.selected_data(name, slot, letter, selection)
        if is_ff or ff5:
            return self.ff_cell(name, slot, letter, ff5, data)
        return {"op": "alias", "input": data}

    def build_virtual(self, node):
        kind, name, slot, *tail = node
        if kind == "lut":
            return self.lut_cell(name, slot, *tail)
        if kind in ("unresolved", "unsupported"):
            return {"op": "boundary", "reason": kind}
        fs = self.site_features(name, slot)
        if kind == "ci":
            index = tail[0]
            if index:
                return {"op": "alias", "input": ("co", name, slot, index - 1)}
            selected = [f[10:] for f in fs if f.startswith("PRECYINIT.")]
            if len(selected) != 1:
                return {"op": "boundary", "reason": "没有唯一进位输入"}
            mode = selected[0]
            src = int(mode[1]) if mode in ("C0", "C1") else self.pin_source(name, slot, mode)
            return {"op": "alias", "input": src}
        if kind in ("co", "xor"):
            index = tail[0]
            letter = "ABCD"[index]
            select = ("lut", name, slot, letter, 6)
            carry = ("ci", name, slot, index)
            if kind == "xor":
                return {"op": "xor", "inputs": (select, carry)}
            di = (("lut", name, slot, letter, 5) if "CARRY4." + letter + "CY0" in fs
                  else self.pin_source(name, slot, letter + "X"))
            return {"op": "mux", "inputs": (select, di, carry)}
        if kind == "f7":
            letter = tail[0]
            left, right = ("B", "A") if letter == "A" else ("D", "C")
            return {"op": "mux", "inputs": (self.pin_source(name, slot, letter + "X"),
                    ("lut", name, slot, left, 6), ("lut", name, slot, right, 6))}
        if kind == "f8":
            return {"op": "mux", "inputs": (self.pin_source(name, slot, "BX"),
                    ("f7", name, slot, "C"), ("f7", name, slot, "A"))}
        return {"op": "boundary", "reason": "未覆盖的内部资源"}

    def cell(self, node):
        if isinstance(node, int):
            if node not in (0, 1):
                raise ValueError("单比特常量只能为 0 或 1")
            return {"op": "constant", "value": node}
        if node not in self.cells:
            self.cells[node] = self.build_physical(node) if len(node) == 2 else self.build_virtual(node)
        return self.cells[node]

    def evaluate(self, node, values, cache=None, pending=None):
        """计算组合值。values 必须显式给出所需触发器输出和边界；不推测运行态。"""
        if cache is None:
            cache = {}
        if pending is None:
            pending = set()
        if node in values:
            value = values[node]
            if value not in (0, 1):
                raise ValueError("输入必须为单比特")
            return value
        if node in cache:
            return cache[node]
        if node in pending:
            raise ValueError("遇到未解释的组合环: " + repr(node))
        pending.add(node)
        cell = self.cell(node)
        op = cell["op"]
        get = lambda ref: self.evaluate(ref, values, cache, pending)
        if op == "constant":
            result = cell["value"]
        elif op == "alias":
            result = get(cell["input"])
        elif op == "table":
            index = sum(get(ref) << bit for bit, ref in enumerate(cell["inputs"]))
            result = (cell["truth"] >> index) & 1
        elif op == "xor":
            result = get(cell["inputs"][0]) ^ get(cell["inputs"][1])
        elif op == "mux":
            select, zero, one = cell["inputs"]
            result = get(one if get(select) else zero)
        else:
            raise KeyError("需要显式触发器状态或边界值: " + repr(node))
        pending.remove(node)
        cache[node] = result
        return result

    def leaves(self, node, limit=4000):
        todo, seen, leaves = [node], set(), {}
        while todo:
            item = todo.pop()
            if item in seen:
                continue
            seen.add(item)
            if len(seen) > limit:
                raise ValueError("组合依赖超过本次上限")
            cell = self.cell(item)
            op = cell["op"]
            if op in ("ff", "boundary"):
                leaves[item] = cell
            elif op == "alias":
                todo.append(cell["input"])
            elif op in ("table", "xor", "mux"):
                todo.extend(cell["inputs"])
        return leaves

    def restrict(self, root, known):
        """按显式常量化简组合锥，保留所有其余触发器和未知边界。"""
        if any(value not in (0, 1) for value in known.values()):
            raise ValueError("约束必须为单比特")
        memo, reduced, pending = {}, {}, set()

        def visit(node):
            if node in known:
                return known[node]
            if isinstance(node, int):
                return node
            if node in memo:
                return memo[node]
            if node in pending:
                raise ValueError("未解释的组合环")
            pending.add(node)
            cell = self.cell(node)
            op = cell["op"]
            if op in ("ff", "boundary"):
                result = node
                reduced[node] = cell
            elif op == "constant":
                result = cell["value"]
            elif op == "alias":
                result = visit(cell["input"])
            else:
                inputs = [visit(ref) for ref in cell["inputs"]]
                if op == "table":
                    table = reduced_table(inputs, cell["truth"])
                elif op == "xor":
                    table = reduced_table(inputs, 0x6)
                elif op == "mux":
                    # 索引位依次为 select、zero、one；真值表为 0xe4。
                    table = reduced_table(inputs, 0xe4)
                else:
                    raise ValueError("未覆盖的组合运算: " + op)
                if not table["inputs"]:
                    result = table["truth"]
                elif len(table["inputs"]) == 1 and table["truth"] == 2:
                    result = table["inputs"][0]
                else:
                    result = node
                    reduced[node] = table
            pending.remove(node)
            memo[node] = result
            return result

        result = visit(root)
        todo, reachable, leaves = [result], {}, {}
        while todo:
            node = todo.pop()
            if isinstance(node, int) or node in reachable:
                continue
            cell = reduced[node]
            reachable[node] = cell
            if cell["op"] in ("ff", "boundary"):
                leaves[node] = cell
            else:
                todo.extend(cell["inputs"])
        return result, reachable, leaves
