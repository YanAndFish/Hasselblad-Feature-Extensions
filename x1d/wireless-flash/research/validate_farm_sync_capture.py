"""从固定官方输入重跑 ARM 同步捕获测试，仅写本模块验证报告。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
if Path.cwd().resolve() != ROOT:
    raise RuntimeError("Run from the authorized project directory")
sys.path.insert(0, str(ROOT / ".research-cache/x1d-1.25.0/python"))
sys.path.insert(0, str(ROOT / "x1d/tools"))
from farm_diagnostic_binary import FarmApplication


def run():
    farm = FarmApplication()
    path = HERE / "CodeTests/test_farm_sync_capture.py"
    spec = importlib.util.spec_from_file_location("sync_capture_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FARM = farm.data
    output = HERE / "build/farm-sync-capture"
    report = {"farm_sha256": farm.sha256, "hardware_requests": 0,
              "installed": False, "physical_timing_measured": False}
    passed = True
    for variant in ("simulation", "target"):
        module.ELF_PATH = output / (variant + ".elf")
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(module))
        report[variant + "_tests"] = result.testsRun
        report[variant + "_passed"] = result.wasSuccessful()
        report[variant + "_log"] = log.getvalue()
        report[variant + "_elf_sha256"] = hashlib.sha256(module.ELF_PATH.read_bytes()).hexdigest()
        passed &= result.wasSuccessful() and result.testsRun == 14
    names = ("CodeTests/test_farm_sync_capture.py", "native/farm_sync_capture.c",
             "native/farm_sync_capture_hooks.S", "native/farm_sync_wire.h",
             "research/build_farm_sync_capture.py", "research/validate_farm_sync_capture.py")
    report["source_hashes"] = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names}
    report["payload_sha256"] = hashlib.sha256((output / "target.bin").read_bytes()).hexdigest()
    report["passed"] = passed
    (output / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loader_path = HERE / "CodeTests/test_farm_sync_loader.py"
    loader_spec = importlib.util.spec_from_file_location("sync_loader_test", loader_path)
    loader_module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(loader_module)
    loader_module.FARM = farm.data
    loader_log = io.StringIO()
    loader_result = unittest.TextTestRunner(stream=loader_log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(loader_module))
    loader_names = names + ("research/farm_sync_loader.py", "research/farm_probe_loader.py",
                            "research/farm_probe_preflight.py", "CodeTests/test_farm_sync_loader.py")
    loader_report = {"passed": loader_result.wasSuccessful(), "tests": loader_result.testsRun,
                     "log": loader_log.getvalue(), "hardware_requests": 0,
                     "payload_sha256": report["payload_sha256"],
                     "source_hashes": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                       for name in loader_names}}
    (output / "loader-validation.json").write_text(json.dumps(loader_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed &= loader_result.wasSuccessful()
    print(json.dumps({"loader_passed": loader_result.wasSuccessful(), "loader_tests": loader_result.testsRun}))
    if not loader_result.wasSuccessful():
        print(loader_log.getvalue())
    print(json.dumps({key: value for key, value in report.items() if key in
                     ("passed", "simulation_tests", "target_tests", "hardware_requests")}))
    if not passed:
        print(report["simulation_log"] + report["target_log"])
        raise SystemExit(1)


if __name__ == "__main__":
    run()
