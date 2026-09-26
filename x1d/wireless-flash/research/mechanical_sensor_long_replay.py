"""对已核对的局部传感器模型做多帧电脑端回放，不生成相机可加载程序。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

from fpga_cycle_model import compile_half_step, freeze, run_explicit_case
from fpga_native_replay import replay_source
from mechanical_sensor_modes import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def run():
    assert Path.cwd().resolve() == ROOT
    snapshot, cases, metadata = prepare(cycles=80000, controls=(3, 7, 0x302), waveforms=('zero', 'rise100'))
    # 独立短例核对本轮生成、输出解析及最终状态，不以事件摘要代替验证。
    check = copy.deepcopy(cases[0])
    check['cycles'] = 1600
    cases.append(check)
    source = replay_source(snapshot, cases, compile_half_step, freeze)
    build = HERE.parent / 'build/mechanical-sensor-replay'
    build.mkdir(exist_ok=True)
    src, exe = build / 'replay.c', build / 'replay.exe'
    src.write_text(source, encoding='utf-8')
    compiler = ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    environment = os.environ.copy()
    environment['ZIG_LOCAL_CACHE_DIR'] = str(build / 'local-cache')
    environment['ZIG_GLOBAL_CACHE_DIR'] = str(build / 'global-cache')
    subprocess.run([str(compiler), 'cc', '-O2', str(src), '-o', str(exe)], env=environment, check=True, timeout=120, capture_output=True)
    output = subprocess.run([str(exe)], check=True, timeout=120, capture_output=True, text=True).stdout
    events = [[] for _ in cases]
    finals = {}
    for line in output.splitlines():
        fields = line.split(',')
        if fields[0] == 'EVENT':
            events[int(fields[1])].append((int(fields[2]), tuple(map(int, fields[3]))))
        elif fields[0] == 'FINAL':
            finals[int(fields[1])] = list(map(int, fields[2]))
        else:
            raise ValueError('未识别的模型输出')
    assert len(finals) == len(cases)
    expected_events, expected_final = run_explicit_case(snapshot, check)
    assert events[-1] == expected_events and finals[len(cases)-1] == expected_final
    result = metadata | {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                         'short_python_comparison': '全部事件和最终状态一致', 'cases': []}
    for index, case in enumerate(cases[:-1]):
        changes = []
        for probe in range(len(case['probes'])):
            prior = None
            observed = []
            for tick, values in events[index]:
                if prior != values[probe]:
                    observed.append((tick, values[probe]))
                    prior = values[probe]
            changes.append(observed)
        result['cases'].append({key: case[key] for key in ('name', 'mode', 'control', 'waveform')} |
                               {'changes_by_probe': changes, 'events': events[index],
                                'final_probes': [finals[index][snapshot.indices[n]] for n in case['probes']]})
    (HERE / 'mechanical-sensor-long-replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('多帧案例', len(result['cases']), '短例对照通过；硬件请求0')
    for case in result['cases']:
        if case['waveform'] == 'zero' or case['control'] == 0x302:
            print(case['name'], 'B', case['changes_by_probe'][3][:9], 'start', case['changes_by_probe'][0][:7])


if __name__ == '__main__':
    run()
