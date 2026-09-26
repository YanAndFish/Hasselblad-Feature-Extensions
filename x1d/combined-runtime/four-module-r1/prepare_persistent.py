"""创建当前固件永久版工作副本；不运行或改变相机。"""
from pathlib import Path
import hashlib,json,shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=HERE/'mechanical-calibration-r1'
DEST=HERE/'persistent-r1'

def main():
    if Path.cwd().resolve()!=ROOT or DEST.exists():
        raise RuntimeError('workspace mismatch or candidate already exists')
    proof=json.loads((SOURCE/'update/final-result.json').read_text())
    if not proof['installed'] or not proof['afAndFlashPreserved']:
        raise RuntimeError('accepted temporary installation evidence required')
    for name in ('native','qml','research'):
        shutil.copytree(SOURCE/name,DEST/name,ignore=shutil.ignore_patterns('__pycache__'))
    (DEST/'CodeTests').mkdir()
    (DEST/'build/formal-flash-candidate').mkdir(parents=True)
    for name in ('formal_flash_hashes.h','formal_flash_lut.h'):
        shutil.copyfile(SOURCE/'build/formal-flash-candidate'/name,DEST/'build/formal-flash-candidate'/name)
    for name in ('build_candidate.py','run_checks.py'):
        shutil.copyfile(SOURCE/name,DEST/name)
    for p in (SOURCE/'CodeTests').iterdir():
        if p.is_file() and p.suffix in ('.py','.cpp','.h'):
            shutil.copyfile(p,DEST/'CodeTests'/p.name)
    for p in (SOURCE/'CodeTests').iterdir():
        if p.is_dir() and p.name not in ('__pycache__','output') and 'fake' in p.name:
            shutil.copytree(p,DEST/'CodeTests'/p.name)
    inputs={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest()
            for name in ('native','qml') for p in (SOURCE/name).rglob('*') if p.is_file()}
    (DEST/'accepted-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    print('Created persistent candidate from accepted calibration sources; hardware requests=0')

if __name__=='__main__':main()
