"""比较控制清同步保持位前后局部曝光状态；不推断实测时序。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from fpga_cycle_model import Snapshot, freeze
from fpga_sticky_sync import compare_cases

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "build/farm-sync-capture"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run():
    original = read(HERE / "research/fpga-sensorif-netlist.json")
    extended = read(OUT / "fpga-sync-netlist.json")
    snapshot = Snapshot(extended)
    evidence = read(HERE / "research/fpga-sensorif-evidence.json")
    data = {bit: freeze(evidence["write_data_captures"]["PS7_MAXIGP0WDATA" + str(bit)]) for bit in (0, 1, 6)}
    probes = [("CLBLM_R_X63Y66", "CLBLM_M_AQ"),
              ("CLBLM_R_X65Y69", "CLBLM_M_AQ"),
              ("CLBLM_R_X63Y69", "CLBLM_L_BQ"),
              ("CLBLM_R_X71Y65", "CLBLM_L_BQ")]

    def case(source, clear):
        result = deepcopy(source)
        result["name"] += "_clear" if clear else "_original"
        result["initial_boundary_values"].append([data[6], 0])
        new = []
        for cycle, source_cycle in ((6, 10), (7, 11)):
            values = {freeze(n): v for n, v in next(u["values"] for u in result["boundary_updates"] if u["cycle"] == source_cycle)}
            values.update({data[0]: 0, data[1]: 0, data[6]: int(clear)})
            new.append({"cycle": cycle, "values": list(values.items())})
        for update in result["boundary_updates"]:
            if update["cycle"] >= 10:
                update["values"].append([data[6], 0])
        result["boundary_updates"] = sorted(result["boundary_updates"] + new, key=lambda u: u["cycle"])
        return result

    pairs, results = [], []
    for source in read(HERE / "research/fpga-sensorif-replay.json")["cases"]:
        baseline, candidate = case(source, False), case(source, True)
        result = compare_cases(snapshot, [e["node"] for e in original["state_cells"]], baseline, candidate, probes)
        events = result["candidateEvents"]
        old = any(c < 6 and v[1] == 1 for c, v in events)
        cleared = any(6 <= c < 10 and v[1] == 0 for c, v in events)
        fresh = any(c > 10 and v[1] == 1 for c, v in events)
        result["old_sticky_present"] = old
        result["old_sticky_cleared_before_start"] = cleared
        result["new_sticky_after_start"] = fresh
        result["passed"] = result["originalStatesIdentical"] and old and cleared and fresh
        pairs.append({"baseline": baseline, "candidate": candidate})
        results.append(result)
    fanout = read(OUT / "fpga-clear-fanout.json")
    fanout_ok = fanout["coveredGraphExhausted"] and not fanout["original_state_intersection"] and not any(e["special"] for e in fanout["nodes"])
    names = ("research/fpga-sensorif-netlist.json", "research/fpga-sensorif-replay.json",
             "research/fpga-sensorif-evidence.json", "research/fpga-database-manifest.json",
             "research/fpga_cycle_model.py", "research/fpga_sticky_sync.py",
             "research/restore_fpga_sync_model.py", "research/validate_fpga_sync_model.py",
             "build/farm-sync-capture/fpga-sync-netlist.json", "build/farm-sync-capture/fpga-clear-fanout.json")
    report = {"passed": all(r["passed"] for r in results) and fanout_ok,
              "original_states_identical": all(r["originalStatesIdentical"] for r in results),
              "local_clear_fanout_verified": fanout_ok, "cases": results,
              "hardware_requests": 0, "physical_timing_measured": False,
              "scope": "固定配置的局部时钟模型；不等于完整 AXI 或电气测量",
              "source_hashes": {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in names}}
    for name, document in (("fpga-validation.json", report), ("fpga-sync-cases.json", pairs)):
        (OUT / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": len(results), "original_states_identical": report["original_states_identical"]}))
    if not report["passed"]:
        print(json.dumps(results))
        raise SystemExit(1)


if __name__ == "__main__":
    run()
