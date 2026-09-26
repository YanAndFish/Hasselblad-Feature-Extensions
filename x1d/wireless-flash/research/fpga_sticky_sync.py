"""将已核对的同步保持支路加入离线模型；没有文件或设备访问。

新增边界必须由调用方明确提供，新增触发器逐个核对时钟来源。
状态比较只覆盖导出的局部模型，不代表电气测量或完整 AXI 仿真。
"""

from copy import deepcopy


def extend_snapshot(document, logic, route, roots, explicit_boundaries):
    result = deepcopy(document)
    freeze = lambda value: tuple(map(freeze, value)) if isinstance(value, list) else value
    present = {freeze(entry["node"]) for group in
               ("state_cells", "boundary_cells", "combinational_cells")
               for entry in result[group]}
    source = freeze(document["clock_source"])
    clock_checks = []
    for node, description in explicit_boundaries.items():
        if node in present:
            raise ValueError("新增边界与已有节点重复")
        result["boundary_cells"].append({"node": node,
                                        "cell": {"op": "boundary", "reason": description}})
        present.add(node)

    def visit(node):
        if isinstance(node, int) or node in present:
            return
        if len(present) > 7000:
            raise ValueError("支路超出本次模型边界")
        cell = logic.cell(node)
        if cell["op"] == "boundary":
            raise ValueError("未指定的新边界: " + repr(node))
        present.add(node)
        if cell["op"] == "ff":
            if cell["latch"]:
                raise ValueError("不支持 latch")
            clock_nodes, _ = route.trace(cell["clock_pin"], backwards=True)
            if source not in clock_nodes:
                raise ValueError("新增状态未确认共享时钟: " + repr(node))
            clock_checks.append({"node": node, "clockPin": cell["clock_pin"],
                                 "source": source, "routeNodeCount": len(clock_nodes)})
            group, refs = "state_cells", [cell[key] for key in ("d", "ce", "sr")]
        else:
            group = "combinational_cells"
            refs = [cell["input"]] if cell["op"] == "alias" else cell.get("inputs", [])
        result[group].append({"node": node, "cell": cell})
        for ref in refs:
            visit(ref)

    for root in roots:
        visit(root)
    result["extension_clock_checks"] = clock_checks
    result["extension_roots"] = roots
    return result


def compare_cases(snapshot, original_states, baseline, candidate, probes):
    """同周期比较原曝光状态；仅记录新支路/探针变化，避免巨量逐周期日志。"""
    freeze = lambda value: tuple(map(freeze, value)) if isinstance(value, list) else value
    if baseline["cycles"] != candidate["cycles"]:
        raise ValueError("比较长度必须相同")
    streams = []
    for case in (baseline, candidate):
        values = snapshot.initial_values({freeze(node): value for node, value
                                          in case["initial_boundary_values"]})
        updates = {}
        for change in case["boundary_updates"]:
            updates.setdefault(change["cycle"], []).extend(change["values"])
        streams.append((values, updates))
    original = [snapshot.indices[freeze(node)] for node in original_states]
    probe_indices = [snapshot.indices[freeze(node)] for node in probes]
    events, previous, mismatches = [[], []], [None, None], []
    for cycle in range(baseline["cycles"]):
        for number, (values, updates) in enumerate(streams):
            for node, value in updates.get(cycle, []):
                node = freeze(node)
                if node not in snapshot.boundaries or value not in (0, 1):
                    raise ValueError("只接受明确的单比特边界赋值")
                values[snapshot.indices[node]] = value
            snapshot.sampled_cycle(values)
            observation = tuple(values[index] for index in probe_indices)
            if observation != previous[number]:
                events[number].append((cycle, observation))
                previous[number] = observation
        changed = [index for index in original if streams[0][0][index] != streams[1][0][index]]
        if changed and len(mismatches) < 8:
            mismatches.append({"cycle": cycle, "indices": changed})
    return {"name": candidate["name"], "cycles": baseline["cycles"],
            "originalStateCount": len(original), "originalStatesIdentical": not mismatches,
            "firstMismatches": mismatches, "probes": probes,
            "baselineEvents": events[0], "candidateEvents": events[1],
            "physicalTimingMeasured": False, "hardwareRequests": 0}
