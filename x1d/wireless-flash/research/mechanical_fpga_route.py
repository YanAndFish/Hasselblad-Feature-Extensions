"""重建机械同步研究用的官方 FPGA 布线对象，仅使用已缓存的固定输入。"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def load():
    assert Path.cwd().resolve() == ROOT
    sys.path.insert(0, str(ROOT / ".research-cache/x1d-1.25.0/python"))
    sys.path.insert(0, str(ROOT / "x1d/tools"))
    sys.path.insert(0, str(HERE / "research"))
    from fpga_bitstream import analyze, parse_packets
    from fpga_frames import map_frames
    from fpga_routing import Routing
    from fpga_clock_io import routing_class
    from fpga_logic import Logic
    from farm_diagnostic_binary import HASHES
    manifest = json.loads((HERE / "research/fpga-database-manifest.json").read_text(encoding="utf-8"))
    entries = dict(manifest["resources"])
    entries.update({key: manifest["sources"][key] for key in ("part", "tilegrid", "tileconn")})
    files = {}
    for name, expected in entries.items():
        data = (HERE / "build/farm-sync-capture/public-database" / name).read_bytes()
        assert len(data) == expected["bytes"] and hashlib.sha256(data).hexdigest() == expected["sha256"]
        files[name] = data
    extension = json.loads((HERE / "research/mechanical-fpga-database-extension.json").read_text(encoding="utf-8"))
    assert extension["database_commit"] == manifest["database_commit"]
    for name, expected in extension["resources"].items():
        assert name == "ppips_brkh_int.db"
        data = (HERE / "research" / name).read_bytes()
        assert len(data) == expected["bytes"] and hashlib.sha256(data).hexdigest() == expected["sha256"]
        assert all(line.endswith(" always") for line in data.decode("ascii").splitlines())
        files[name] = data
    spec = importlib.util.spec_from_file_location("mechanical_fixed_input", ROOT / "x1d/recovery-review/20260910-usb-sd/inspect_payloads.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    reader.WANTED = set(HASHES)
    inputs = reader.inputs()
    for name, expected in HASHES.items():
        assert hashlib.sha256(inputs[name]).hexdigest() == expected
    even = next(data for name, data in inputs.items() if "bootimage_even" in name)
    odd = next(data for name, data in inputs.items() if "bootimage_odd" in name)
    spread = [sum(((v >> bit) & 1) << (2 * bit) for bit in range(8)) for v in range(256)]
    boot = b"".join((spread[e] | (spread[o] << 1)).to_bytes(2, "big") for e, o in zip(even, odd))
    meta = analyze(boot)
    raw = boot[meta["pl_offset"]:meta["pl_offset"] + meta["pl_bytes"]]
    frames, _ = map_frames(raw, json.loads(files["part"]), parse_packets(raw))
    route = routing_class(Routing)(frames, json.loads(files["tilegrid"]), json.loads(files["tileconn"]), files)
    return route, Logic(route), meta
