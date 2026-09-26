"""重建固定 FPGA 局部模型的同步保持支路；仅电脑离线操作。"""
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import urllib.request

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(ROOT / ".research-cache/x1d-1.25.0/python"))
sys.path.insert(0, str(ROOT / "x1d/tools"))
from fpga_bitstream import analyze, parse_packets
from fpga_frames import map_frames
from fpga_routing import Routing
from fpga_clock_io import routing_class
from fpga_logic import Logic
from fpga_sticky_sync import extend_snapshot
from fpga_sync_observability import explore


def run():
    out = HERE / "build/farm-sync-capture"
    cache = out / "public-database"
    cache.mkdir(exist_ok=True)
    manifest = json.loads((HERE / "research/fpga-database-manifest.json").read_text(encoding="utf-8"))
    entries = dict(manifest["resources"])
    entries.update({k: manifest["sources"][k] for k in ("part", "tilegrid", "tileconn")})

    def get(item):
        name, meta = item
        path = cache / name
        data = path.read_bytes() if path.exists() else urllib.request.urlopen(meta["url"], timeout=45).read()
        if len(data) != meta["bytes"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError("Public input mismatch: " + name)
        if not path.exists():
            path.write_bytes(data)
        return name, data

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        files = dict(pool.map(get, entries.items()))
    print("Public database inputs verified", len(files), flush=True)
    spec = importlib.util.spec_from_file_location("fixed_input_reader", ROOT / "x1d/recovery-review/20260910-usb-sd/inspect_payloads.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    from farm_diagnostic_binary import HASHES
    reader.WANTED = set(HASHES)
    inputs = reader.inputs()
    for name, digest in HASHES.items():
        assert hashlib.sha256(inputs[name]).hexdigest() == digest
    even = next(b for n, b in inputs.items() if "bootimage_even" in n)
    odd = next(b for n, b in inputs.items() if "bootimage_odd" in n)
    spread = [sum(((v >> bit) & 1) << (2 * bit) for bit in range(8)) for v in range(256)]
    boot = b"".join((spread[e] | (spread[o] << 1)).to_bytes(2, "big") for e, o in zip(even, odd))
    meta = analyze(boot)
    raw = boot[meta["pl_offset"]:meta["pl_offset"] + meta["pl_bytes"]]
    frames, padding = map_frames(raw, json.loads(files["part"]), parse_packets(raw))
    route = routing_class(Routing)(frames, json.loads(files["tilegrid"]), json.loads(files["tileconn"]), files)
    logic = Logic(route)
    document = json.loads((HERE / "research/fpga-sensorif-netlist.json").read_text(encoding="utf-8"))
    roots = [("CLBLM_R_X63Y66", "CLBLM_M_AQ"),
             ("CLBLM_R_X65Y69", "CLBLM_M_AQ"),
             ("CLBLM_R_X63Y69", "CLBLM_L_BQ")]
    boundary = ("CLBLL_L_X72Y61", "CLBLL_LL_AQ")
    extended = extend_snapshot(document, logic, route, roots, {boundary: "已核对 PS7 写数据 bit6 捕获层，显式输入"})
    extended["input_manifest_sha256"] = hashlib.sha256((HERE / "research/fpga-database-manifest.json").read_bytes()).hexdigest()
    (out / "fpga-sync-netlist.json").write_text(json.dumps(extended, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"states": len(extended["state_cells"]), "boundaries": len(extended["boundary_cells"]), "new_clock_checks": len(extended["extension_clock_checks"])}), flush=True)
    fanout = explore(route, logic, roots[0], max_depth=16, max_nodes=700)
    original = {tuple(e["node"]) for e in document["state_cells"]}
    reached = {tuple(e["seed"]) for e in fanout["nodes"]}
    fanout["original_state_intersection"] = sorted(original & reached)
    fanout["pl_sha256"] = meta["pl_sha256"]
    (out / "fpga-clear-fanout.json").write_text(json.dumps(fanout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fanout_nodes": len(fanout["nodes"]), "frontier": len(fanout["frontier"]), "original_state_intersection": len(original & reached)}), flush=True)


if __name__ == "__main__":
    run()
