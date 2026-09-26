"""真实发送线程＋进程内套接字替身；不访问硬件，不写旧验证报告。"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'CodeTests/formal_direct_output'
def run():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('workspace mismatch')
    OUT.mkdir(exist_ok=True)
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        path=OUT/name;path.mkdir(exist_ok=True);env[key]=str(path)
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    executable=OUT/'formal-direct-check.test.exe'
    command=[str(compiler),'c++','-std=c++11','-O2','-Wall','-Wextra','-Werror','-I',str(HERE/'CodeTests'),
             str(HERE/'CodeTests/formal_direct_check.test.cpp'),'-o',str(executable)]
    compiled=subprocess.run(command,capture_output=True,text=True,env=env,timeout=120)
    if compiled.returncode: raise RuntimeError(compiled.stderr)
    result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=20)
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)
    match=re.search(r'formal-direct-host-checks=(\d+) hardware-requests=0',result.stdout)
    if not match: raise RuntimeError('missing host result')
    names=('native/formal_direct_check.h','native/formal_client_check.cpp','native/mechanical_direct_dispatch.h',
           'CodeTests/formal_direct_check.test.cpp','CodeTests/formal_direct_fake_platform.h',
           'CodeTests/mechanical_direct_fake_platform.h','CodeTests/formal_direct_build.py')
    report={'passed':True,'checks':int(match[1]),'hardwareRequests':0,'installed':False,'targetSelfCheckRun':False,
            'stdout':result.stdout,'targetStdout':'formal-direct-check=8 policy=fifo priority=1 camera-requests=0\n',
            'sourceHashes':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in names},
            'compiler':{'arguments':command,'exit':compiled.returncode,'stderr':compiled.stderr}}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return {'passed':True,'checks':report['checks'],'hardwareRequests':0}
if __name__=='__main__': print(json.dumps(run()))
