"""默认离线；显式入口只暂存并执行纯内存协议自检，不启动蓝牙。"""
from pathlib import Path
from datetime import datetime, timezone
import ast
import base64
import gzip
import hashlib
import importlib.util
import json
import shlex
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REMOTE = "/tmp/x1d-bt-r1"
TRANSPORT = ROOT / "x1d/wireless-flash/research/fpga_sync_session.py"
TRANSPORT_SHA = "728b5c282609ccc574eb6591690e8f6b1c711eeb63d981a48a1e5c6dd7b697f7"
DECODER_SOURCE = ROOT / "x1d/candidates/ui-resident/session/delivery.py"
DECODER_SHA = "69a1045dcfdf328ae455ab05f3833292cd0e5b3eb7ea8c0da62b68d8586c78f4"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(report_file=None):
    if Path.cwd().resolve() != ROOT:
        raise ValueError("workspace mismatch")
    report = json.loads((report_file or HERE / "build/validation.json").read_text(encoding="utf-8"))
    for name, sha in report["sources"].items():
        p = (HERE / name).resolve()
        if not p.is_relative_to(HERE) or digest(p.read_bytes()) != sha:
            raise ValueError("source identity mismatch")
    entry = report["artifacts"]["arm"]
    binary_path = (HERE / entry["path"]).resolve()
    if not binary_path.is_relative_to(HERE):
        raise ValueError("binary path outside experiment")
    binary = binary_path.read_bytes()
    if digest(binary) != entry["sha256"] or len(binary) != entry["bytes"]:
        raise ValueError("binary identity mismatch")
    data = DECODER_SOURCE.read_bytes()
    if digest(data) != DECODER_SHA:
        raise ValueError("decoder source changed")
    assignments = [n.value for n in ast.parse(data.decode("utf-8")).body
                   if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == "DECODER" for t in n.targets)]
    if len(assignments) != 1:
        raise ValueError("decoder definition mismatch")
    decoder = ast.literal_eval(assignments[0])
    archive = gzip.compress(binary, mtime=0)
    encoded = base64.b64encode(archive).decode("ascii")
    if gzip.decompress(base64.b64decode(encoded)) != binary:
        raise ValueError("offline archive roundtrip")
    commands = []
    def add(label, command):
        if not 1 <= len(command.encode("ascii")) <= 231 or "\n" in command or "\0" in command:
            raise ValueError("USB command framing")
        commands.append((label, command))
    add("memory-mount", "awk '$2==\"/tmp\" {print $3}' /proc/mounts")
    add("new-directory", f"r={REMOTE};umask 077;test ! -e \"$r\" && test ! -L \"$r\" && mkdir -m 700 \"$r\"")
    for i, start in enumerate(range(0, len(decoder), 64)):
        add(f"decoder-{i}", "printf %s " + shlex.quote(decoder[start:start+64]) +
            (" >" if i == 0 else " >>") + REMOTE + "/d.awk")
    add("decoder-hash", f"sha256sum {REMOTE}/d.awk")
    for i, start in enumerate(range(0, len(encoded), 128)):
        add(f"payload-{i}", "printf %s " + shlex.quote(encoded[start:start+128]) +
            (" >" if i == 0 else " >>") + REMOTE + "/p64")
    add("encoded-hash", f"sha256sum {REMOTE}/p64")
    add("decode", "r=" + REMOTE + ";printf '%b' \"$(/usr/bin/od -v -c \"$r/p64\" | /bin/sed 's/^[0-7]* *//' | /usr/bin/awk -f \"$r/d.awk\")\" >\"$r/probe.gz\"")
    add("archive-hash", f"sha256sum {REMOTE}/probe.gz")
    add("unpack", f"r={REMOTE};test ! -e \"$r/probe\" && gzip -dc \"$r/probe.gz\" >\"$r/probe\"")
    add("binary-hash", f"sha256sum {REMOTE}/probe")
    add("memory-self-test", f"chmod 700 {REMOTE}/probe && {REMOTE}/probe --self-test")
    # 删除本轮创建的四个精确文件；不递归清理，外来文件会令 rmdir 失败而保留。
    add("cleanup", f"r={REMOTE};rm \"$r/probe\" \"$r/probe.gz\" \"$r/p64\" \"$r/d.awk\" && rmdir \"$r\"")
    add("cleanup-check", f"test ! -e {REMOTE} && test ! -L {REMOTE} && echo temporary-files-removed")
    expected = {
        "memory-mount": "tmpfs",
        "decoder-hash": digest(decoder.encode()), "encoded-hash": digest(encoded.encode()),
        "archive-hash": digest(archive), "binary-hash": digest(binary),
        "memory-self-test": "offline_hci_self_test=passed;hardware_access=none",
        "cleanup-check": "temporary-files-removed",
    }
    return binary, commands, expected


def execute(binary, commands, expected):
    if digest(TRANSPORT.read_bytes()) != TRANSPORT_SHA:
        raise ValueError("USB source changed")
    spec = importlib.util.spec_from_file_location("bt_memory_usb", TRANSPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    name = "memory-self-test-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = HERE / "build/sessions" / name
    folder.mkdir(parents=True, exist_ok=False)
    session = mod.Session(name + ".json")
    session.output = folder / "usb.json"
    state = {"camera_self_test": "not-complete", "bluetooth_commands_sent": 0,
             "binary_sha256": digest(binary), "temporary_directory": REMOTE}
    try:
        for label, command in commands:
            reply = session.command(label, command, 5000)
            output = reply["output"].strip()
            if len(reply["output"].encode("ascii")) >= 231:
                raise ValueError("possibly truncated USB output")
            if label in expected:
                observed = output.split()[0] if label.endswith("-hash") else output
                if observed != expected[label]:
                    raise ValueError("camera output mismatch: " + label)
            state["last_completed"] = label
            if label == "memory-self-test": state["camera_self_test"] = "passed"
        state["temporary_files_removed"] = True
    except BaseException as error:
        state["failure"] = type(error).__name__
        state["note"] = "停止；未知结果不重发，也不自动补发清理命令。"
        raise
    finally:
        state["all_handles_closed"] = all(e["closed"] for e in session.entries)
        state["requests"] = sum(e["submitted"] for e in session.entries)
        (folder / "result.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        print(json.dumps(state, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    binary, commands, expected = prepare()
    if sys.argv[1:] == ["--run-memory-self-test"]:
        execute(binary, commands, expected)
    elif not sys.argv[1:]:
        print(json.dumps({"offline": True, "framing_and_archive_checks": "passed",
                          "binary_bytes": len(binary), "planned_requests": len(commands),
                          "radio_access": "none"}))
    else:
        raise SystemExit("只支持默认离线验证或 --run-memory-self-test")
