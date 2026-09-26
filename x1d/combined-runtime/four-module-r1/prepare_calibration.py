"""新建标定工作副本；不改已冻结输入，不连接设备。"""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORK = HERE / 'mechanical-calibration-r1'

def main():
    if Path.cwd().resolve() != ROOT or WORK.exists():
        raise RuntimeError('workspace mismatch or candidate already exists')
    shutil.copytree(HERE/'mechanical-exit-idle/native', WORK/'native')
    shutil.copytree(HERE/'mechanical-exit-idle/CodeTests', WORK/'CodeTests', ignore=shutil.ignore_patterns('__pycache__'))
    (WORK/'research').mkdir()
    shutil.copyfile(ROOT/'x1d/wireless-flash/research/build_formal_clients.py', WORK/'research/build_formal_clients.py')
    (WORK/'build/formal-flash-candidate').mkdir(parents=True)
    for name in ('formal_flash_hashes.h', 'formal_flash_lut.h'):
        shutil.copyfile(ROOT/'x1d/wireless-flash/build/formal-flash-candidate'/name, WORK/'build/formal-flash-candidate'/name)
    shutil.copytree(HERE/'build/qml', WORK/'qml')
    print('Created calibration candidate; no device requests')

if __name__ == '__main__':
    main()
