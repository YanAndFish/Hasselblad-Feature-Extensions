"""冻结旧实现对照四路读取；合成数据覆盖环形缓冲回绕、短读及覆盖拒绝。"""
import array
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'x2d/outputs/4.2.0/pixel-shift-rgb/read-parallel-r1'
ZIG = Path(os.environ.get('HFE_ZIG', 'zig'))
ENV = dict(os.environ, TEMP=str(OUT), TMP=str(OUT),
           ZIG_LOCAL_CACHE_DIR=str(OUT/'zig-local'), ZIG_GLOBAL_CACHE_DIR=str(OUT/'zig-global'))
WIDTH, HEIGHT = 67, 2059


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def build(source, target, extra):
    subprocess.run([str(ZIG), 'cc', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-DFACTORY_NATIVE_DOMAIN=1', '-I', str(HERE), *extra,
                    str(source), '-o', str(target)], env=ENV, check=True)


def fixture(path, index, frame_count=4):
    header = bytearray(16384)
    header[:8] = b'II*\0'+struct.pack('<I', 8)
    def ifd(offset, tags):
        struct.pack_into('<H', header, offset, len(tags))
        for i, values in enumerate(tags):
            struct.pack_into('<HHII', header, offset+2+12*i, *values)
    ifd(8, [(330, 4, 1, 256), (34665, 4, 1, 512),
            (50721, 10, 9, 1024), (50728, 5, 3, 1104)])
    ifd(256, [(256, 4, 1, 11904), (257, 4, 1, 8842), (258, 3, 1, 16),
              (259, 3, 1, 1), (262, 3, 1, 32803), (277, 3, 1, 1),
              (273, 4, 1, 16384), (279, 4, 1, 210510336),
              (50717, 4, 1, 65535), (50714, 5, 1, 1136)])
    ifd(512, [(37500, 4, 1, 768)])
    ifd(768, [(33, 9, 4, 1152)])
    struct.pack_into('<18i', header, 1024, *([1, 1]*9))
    struct.pack_into('<6I', header, 1104, *([1, 1]*3))
    struct.pack_into('<II', header, 1136, 4096, 1)
    struct.pack_into('<4i', header, 1152, frame_count, index, 0, 0)
    with path.open('xb') as f:
        f.write(header)
        for y in range(93+HEIGHT):
            row = array.array('H', ((x*251+y*17+index*10007)&65535 for x in range(11904)))
            f.write(row.tobytes())
        f.truncate(16384+210510336)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = HERE/'Fixtures/frozen-row-merge'
    baseline = frozen/'baseline-onboard-four.c'
    assert digest(baseline) == 'd5e0bab99e70efb363a9d54ca1d66f5672f80e468ce446284ad47a373492d626'
    small_baseline = OUT/'baseline-small.c'
    small_baseline.write_text(baseline.read_text(encoding='utf-8').replace('#define W 11663', f'#define W {WIDTH}')
                             .replace('#define H 8749', f'#define H {HEIGHT}'), encoding='utf-8')
    (OUT/'onboard_six_rows.inc').write_bytes((frozen/'onboard_six_rows.inc').read_bytes())
    build(small_baseline, OUT/'baseline-small.exe', [])
    build(HERE/'onboard_four.c', OUT/'reader-small.exe',
          ['-DFACTORY_PARALLEL_READ=1', f'-DFACTORY_TEST_WIDTH={WIDTH}', f'-DFACTORY_TEST_HEIGHT={HEIGHT}'])
    build(HERE/'onboard_four.c', OUT/'writer-fail.exe',
          ['-DFACTORY_PARALLEL_READ=1', '-DFACTORY_TEST_WRITER_FAIL_AFTER_ROWS=129',
           f'-DFACTORY_TEST_WIDTH={WIDTH}', f'-DFACTORY_TEST_HEIGHT={HEIGHT}'])
    cases = []
    with tempfile.TemporaryDirectory(prefix='synthetic-', dir=OUT) as temp:
        root = Path(temp)
        inputs = [root/f'frame-{i}.3fr' for i in range(4)]
        for i, path in enumerate(inputs):
            fixture(path, i)
        def run(exe, name, args=()):
            return subprocess.run([str(OUT/exe), str(root/name), *map(str, inputs), *args],
                                  capture_output=True, text=True, timeout=45)
        original = run('baseline-small.exe', 'baseline.dng')
        assert original.returncode == 0, original.stderr
        expected = (root/'baseline.dng').read_bytes()
        for name, args in [('seek', ()), ('sequential', ('--sequential-read',)),
                           ('parallel', ('--parallel-read',)),
                           ('compute', ('--compute-threads=4',)),
                           ('pipeline', ('--parallel-read', '--compute-threads=4')),
                           ('writer', ('--parallel-read', '--background-write')),
                           ('all_workers', ('--parallel-read', '--compute-threads=4', '--background-write'))]:
            result = run('reader-small.exe', name+'.dng', args)
            assert result.returncode == 0, result.stderr
            assert (root/(name+'.dng')).read_bytes() == expected
            cases.append(name+'_byte_identical_to_frozen_baseline')
        # 多次消费超过两轮环形容量，线程调度变化仍须逐字节相同。
        for i in range(3):
            result = run('reader-small.exe', f'repeat-{i}.dng', ('--parallel-read', '--compute-threads=4', '--background-write'))
            assert result.returncode == 0 and (root/f'repeat-{i}.dng').read_bytes() == expected
            assert 'MERGE_READER_BATCH_ROWS 1024' in result.stdout
            assert 'MERGE_READER_CALLS 12' in result.stdout
        cases.append('parallel_repeated_ring_wrap_identical')
        result = run('reader-small.exe', 'parallel.dng', ('--parallel-read',))
        assert result.returncode != 0 and (root/'parallel.dng').read_bytes() == expected
        cases.append('existing_output_preserved')
        result = run('writer-fail.exe', 'writer-fail.dng',
                     ('--parallel-read', '--compute-threads=4', '--background-write'))
        assert result.returncode != 0 and 'ONBOARD_FOUR_COMPLETE' not in result.stdout
        assert 'background' in result.stderr, result.stderr
        cases.append('background_write_failure_no_deadlock_or_success')
        # 生产线程在读完缓冲之前遇到短读，也要唤醒主线程并有界结束。
        with inputs[2].open('r+b') as f:
            f.truncate(16384+(93+150)*23808-1)
        result = run('reader-small.exe', 'short.dng', ('--parallel-read', '--compute-threads=4', '--background-write'))
        assert result.returncode != 0 and 'parallel RAW row read' in result.stderr
        assert 'ONBOARD_FOUR_COMPLETE' not in result.stdout
        cases.append('producer_short_read_exits_without_deadlock_or_success')
    # 六张使用原逐行算法作对照，验证第 5/6 张行偏移和跨区段邻域。
    build(small_baseline, OUT/'baseline-six.exe', ['-DFACTORY_SIX=1'])
    build(HERE/'onboard_four.c', OUT/'pipeline-six.exe',
          ['-DFACTORY_SIX=1', '-DFACTORY_PARALLEL_READ=1',
           f'-DFACTORY_TEST_WIDTH={WIDTH}', f'-DFACTORY_TEST_HEIGHT={HEIGHT}'])
    with tempfile.TemporaryDirectory(prefix='synthetic-six-', dir=OUT) as temp:
        root = Path(temp)
        inputs = [root/f'frame-{i}.3fr' for i in range(6)]
        for i, path in enumerate(inputs):
            fixture(path, i, 6)
        def sixrun(exe, name, args=()):
            return subprocess.run([str(OUT/exe), str(root/name), *map(str, inputs), *args],
                                  capture_output=True, text=True, timeout=45)
        original = sixrun('baseline-six.exe', 'baseline.dng')
        assert original.returncode == 0, original.stderr
        expected = (root/'baseline.dng').read_bytes()
        for name, args in [('seek', ()), ('sequential', ('--sequential-read',)),
                           ('parallel', ('--parallel-read',)),
                           ('compute', ('--compute-threads=4',)),
                           ('pipeline', ('--parallel-read', '--compute-threads=4')),
                           ('writer', ('--parallel-read', '--background-write')),
                           ('all_workers', ('--parallel-read', '--compute-threads=4', '--background-write'))]:
            result = sixrun('pipeline-six.exe', name+'.dng', args)
            assert result.returncode == 0, result.stderr
            assert (root/(name+'.dng')).read_bytes() == expected
            if '--parallel-read' in args:
                assert 'MERGE_READER_BATCH_ROWS 1024' in result.stdout
                assert 'MERGE_READER_CALLS 18' in result.stdout
            cases.append('six_'+name+'_byte_identical')
        for index in (4, 5):
            with inputs[index].open('r+b') as f:
                f.truncate(16384+(93+150)*23808-1)
            result = sixrun('pipeline-six.exe', f'short-{index}.dng',
                            ('--parallel-read', '--compute-threads=4'))
            assert result.returncode != 0 and 'ONBOARD_SIX_COMPLETE' not in result.stdout
            assert 'parallel half-grid read' in result.stderr, result.stderr
            inputs[index].unlink()
            fixture(inputs[index], index, 6)
        cases.append('six_half_grid_short_read_no_deadlock')
    build(HERE/'onboard_four.c', OUT/'merge-six-parallel-arm',
          ['-DFACTORY_SIX=1', '-DFACTORY_PARALLEL_READ=1', '-target',
           'aarch64-linux-musl', '-static', '-pthread'])
    build(HERE/'onboard_four.c', OUT/'merge-parallel-arm',
          ['-DFACTORY_PARALLEL_READ=1', '-target', 'aarch64-linux-musl', '-static', '-pthread'])
    report = dict(cases=cases, synthetic_only=True, reader_thread_counts=[4, 6],
                  compute_thread_counts=[1, 4], reader_batch_rows=1024,
                  double_buffered=True,six_ring_memory_bytes=6*2048*11904*2,
                  ring_memory_bytes=4*2048*11904*2, source_sha256=digest(HERE/'onboard_four.c'),
                  reader_sha256=digest(HERE/'four_raw_reader.h'),
                  compute_sha256=digest(HERE/'merge_workers.h'),
                  writer_sha256=digest(HERE/'background_writer.h'),
                  six_source_sha256=digest(HERE/'onboard_six_rows.inc'),
                  six_arm_sha256=digest(OUT/'merge-six-parallel-arm'),
                  arm_sha256=digest(OUT/'merge-parallel-arm'), device_benchmarked=False)
    (OUT/'offline-validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
