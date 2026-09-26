"""追踪离线同步节点的结构扇出；不访问设备，不修改 FPGA 配置。

调用方提供已绑定官方配置与数据库版本的 Routing / Logic 实例。
穿过触发器仅表示下一状态存在依赖，不证明触发时机、电气连通或可用中断。
未知专用资源、CE/SR 依赖和深度限制均保留在报告中。
"""

from collections import deque


def depends(logic, root, source, limit=4000):
    todo, seen = [root], set()
    while todo:
        node = todo.pop()
        if node == source:
            return True
        if node in seen:
            continue
        seen.add(node)
        if len(seen) > limit:
            raise ValueError("组合依赖超过本次上限")
        cell = logic.cell(node)
        if cell["op"] == "alias":
            todo.append(cell["input"])
        elif cell["op"] in ("table", "xor", "mux"):
            todo.extend(cell["inputs"])
        # 触发器在此是边界，不递归穿过状态。
    return False


def fanout(route, logic, seed):
    nodes, _ = route.trace(seed)
    inputs = route.input_sinks(nodes)
    sites = {(pin[0], route.clb_pin(pin)[0]) for pin in inputs}
    for node in nodes:
        pin = route.clb_pin(node)
        if pin and pin[2] in ("CE", "SR", "CIN", "AI", "BI", "CI", "DI"):
            sites.add((node[0], pin[0]))
    special = sorted(node for node in nodes if node[1].startswith("PS7_")
                     or "IOB_O" in node[1])
    children, unresolved = [], []
    for tile, slot in sorted(sites):
        terminals = [letter + suffix for letter in "ABCD" for suffix in ("", "Q", "MUX")]
        terminals.append("COUT")
        for terminal in terminals:
                out = route.pin_wire(tile, slot, terminal)
                outgoing, _ = route.trace(out)
                used = route.input_sinks(outgoing) or any(
                    n[1].startswith("PS7_") or "IOB_O" in n[1]
                    or (route.clb_pin(n) and route.clb_pin(n)[2]
                        in ("CE", "SR", "CIN", "AI", "BI", "CI", "DI", "CLK"))
                    for n in outgoing)
                if not used:
                    continue
                cell = logic.cell(out)
                if cell["op"] == "boundary":
                    unresolved.append({"node": out, "reason": cell["reason"]})
                    continue
                refs = {key: cell[key] for key in ("d", "ce", "sr") if key in cell}
                if cell["op"] != "ff":
                    refs = {"combinational": out}
                roles = [key for key, ref in refs.items() if depends(logic, ref, seed)]
                if roles:
                    children.append({"node": out, "kind": cell["op"], "roles": roles})
    return {"seed": seed, "routeNodeCount": len(nodes), "inputs": inputs,
            "special": special, "children": children, "unresolved": unresolved}


def explore(route, logic, seed, max_depth=4, max_nodes=160):
    if not 0 <= max_depth <= 16 or not 1 <= max_nodes <= 2000:
        raise ValueError("探索边界无效")
    queue, seen = deque([(seed, 0)]), {seed}
    reports, frontier = [], []
    while queue:
        node, depth = queue.popleft()
        report = fanout(route, logic, node)
        report["depth"] = depth
        reports.append(report)
        for child in report["children"]:
            target = child["node"]
            if target in seen:
                continue
            if depth == max_depth or len(seen) >= max_nodes:
                frontier.append(target)
                continue
            seen.add(target)
            queue.append((target, depth + 1))
    return {"maxDepth": max_depth, "maxNodes": max_nodes, "nodes": reports,
            "frontier": sorted(set(frontier)), "coveredGraphExhausted": not frontier
            and not any(item["unresolved"] for item in reports),
            "completeDeviceConnectivityProven": False}
