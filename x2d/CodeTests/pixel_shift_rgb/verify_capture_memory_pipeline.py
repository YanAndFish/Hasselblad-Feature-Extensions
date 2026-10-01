"""重建普通字节视图上的内存候选；使用合成材料对照冻结旧版，零设备操作。"""
import array
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'x2d/outputs/4.2.0/pixel-shift-rgb/memory-pipeline-r1'
FROZEN = HERE / 'Fixtures/frozen-row-merge'
ZIG = Path(os.environ.get('HFE_ZIG', 'zig'))
WIDTH, HEIGHT = 67, 2059


def main():
    assert Path.cwd().resolve() == ROOT
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEMP=str(OUT), TMP=str(OUT),
               ZIG_LOCAL_CACHE_DIR=str(OUT / 'zig-local'),
               ZIG_GLOBAL_CACHE_DIR=str(OUT / 'zig-global'))

    def run(args, timeout=120):
        result = subprocess.run([str(a) for a in args], env=env, capture_output=True,
                                text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout.strip()

    def build(source, name, extras=(), arm=False):
        target = OUT / name
        run([ZIG, 'cc', '-O2', '-Wall', '-Wextra', '-Werror', '-I', OUT.parent,
             *(['-target', 'aarch64-linux-musl', '-static'] if arm else []),
             source, *extras, '-o', target])
        return target

    checks = []
    fanout = build(HERE / 'check_pixel_chunk_fanout.c', 'check.exe', ['-pthread'])
    for _ in range(5):
        run([fanout])
    build(HERE / 'check_pixel_chunk_fanout.c', 'check-arm', ['-pthread'], arm=True)
    checks.append('dual-consumer-reference-lifetime-and-backpressure')
    merger = build(HERE / 'check_capture_memory_merge.c', 'merge-check.exe',
                   [HERE / 'capture_memory_merge.c'])
    build(HERE / 'check_capture_memory_merge.c', 'merge-check-arm',
          [HERE / 'capture_memory_merge.c'], arm=True)
    # 冻结的旧版算法保持只读；从既有固定源码重建，避免拿新内存核心自证。
    baseline = build(FROZEN / 'baseline-small.c', 'frozen-six.exe',
                     ['-DFACTORY_SIX=1', '-DFACTORY_NATIVE_DOMAIN=1'])
    current = build(HERE / 'onboard_four.c', 'current-six.exe',
                    ['-DFACTORY_SIX=1', '-DFACTORY_NATIVE_DOMAIN=1',
                     '-DFACTORY_PARALLEL_READ=1', '-pthread',
                     f'-DFACTORY_TEST_WIDTH={WIDTH}', f'-DFACTORY_TEST_HEIGHT={HEIGHT}'])
    run([ZIG, 'cc', '-target', 'aarch64-linux-musl', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
         '-DFACTORY_SIX=1', '-DFACTORY_NATIVE_DOMAIN=1', '-DFACTORY_PARALLEL_READ=1', '-pthread',
         HERE / 'onboard_four.c', '-o', OUT / 'file-merge-refactored-arm'])
    spec = importlib.util.spec_from_file_location('parallel_fixture', HERE / 'verify_parallel_read.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    with tempfile.TemporaryDirectory(prefix='memory-kernel-', dir=OUT) as temp:
        work = Path(temp).resolve()
        work.relative_to(OUT.resolve())
        inputs = []
        # 已有合成 fixture 的头；只生成计算会用到的列，其余行列设零。
        for i in range(6):
            path = work / f'frame-{i}.3fr'
            saved_height = fixture.HEIGHT
            fixture.HEIGHT = 0
            fixture.fixture(path, i, 6)
            fixture.HEIGHT = saved_height
            with path.open('r+b') as stream:
                for y in range(92, 93 + HEIGHT):
                    row = array.array('H', [0]) * 11904
                    for x in range(124, 126 + WIDTH):
                        row[x] = (x * 251 + y * 17 + i * 10007) & 65535
                    stream.seek(16384 + y * 23808)
                    stream.write(row.tobytes())
            inputs.append(path)
        golden = work / 'baseline.dng'
        run([baseline, golden, *inputs])
        new_file = work / 'current.dng'
        run([current, new_file, *inputs])
        assert golden.read_bytes() == new_file.read_bytes(), 'File-path regression'
        threaded = work / 'threaded.dng'
        run([current, threaded, *inputs, '--parallel-read', '--compute-threads=4', '--background-write'])
        assert golden.read_bytes() == threaded.read_bytes(), 'Threaded file-path regression'
        pixels = work / 'memory.bin'
        checks.append(run([merger, pixels]))
        assert pixels.read_bytes() == golden.read_bytes()[4096:], 'Memory/frozen pixel mismatch'
    sources = ['capture_memory_view.h', 'capture_memory_merge.h', 'capture_memory_merge.c',
               'six_row_kernel.h', 'onboard_six_rows.inc', 'pixel_chunk_fanout.h',
               'capture_memory_pipeline.h', 'check_capture_memory_merge.c',
               'verify_capture_memory_pipeline.py']
    report = dict(mode='offline-synthetic-inputs', checks=checks,
                  memory_and_frozen_file_pixels_byte_identical=True,
                  file_path_refactor_byte_identical=True,
                  parallel_read_compute_and_write_refactor_byte_identical=True,
                  tested_batch_rows=[1, 127, 1024], compute_partitions=4,
                  memory_merge_connected_to_dual_output_queue=True,
                  real_capture_writer_and_renderer_connected=False,
                  installed=False, device_requests=0,
                  source_sha256={name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                 for name in sources},
                  frozen_sources_sha256={name: hashlib.sha256((FROZEN / name).read_bytes()).hexdigest()
                                        for name in ('baseline-small.c', 'onboard_six_rows.inc')})
    (OUT / 'pipeline-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('MEMORY_PIPELINE_FIRST_PREVIEW_KERNEL_FROZEN_COMPARISON_AND_ARM_BUILDS_PASSED_NOT_INSTALLED')


if __name__ == '__main__':
    main()
