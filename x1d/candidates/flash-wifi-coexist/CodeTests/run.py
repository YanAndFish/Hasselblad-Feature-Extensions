"""离线编译并执行真实状态机；所有生成物限本候选目录。"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=MODULE.parents[2]
OUT=MODULE/'build/code-tests'

def main():
    if Path.cwd().resolve()!=ROOT:
        raise RuntimeError('workspace mismatch')
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[HERE/'core.test.cpp',MODULE/'native/coexist_core.h',MODULE/'native/link_evidence.h',Path(__file__)]
    hashes={str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TMP','tmp'),('TEMP','tmp')]:
        folder=OUT/name;folder.mkdir(exist_ok=True);env[key]=str(folder)
    exe=OUT/'core.test.exe'
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    report={'passed':False,'hardwareRequests':0,'sourceHashes':hashes}
    path=OUT/'validation.json'
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    subprocess.run([str(zig),'c++','-std=c++11','-O2','-Wall','-Wextra','-Werror',str(HERE/'core.test.cpp'),'-o',str(exe)],env=env,check=True)
    result=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
    count=re.fullmatch(r'checks=(\d+) hardware-requests=0\s*',result.stdout)
    if not count:raise RuntimeError('invalid test report')
    if hashes!={str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:raise RuntimeError('sources changed')
    report.update(passed=True,checks=int(count[1]))
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(result.stdout,end='')

if __name__=='__main__':main()
