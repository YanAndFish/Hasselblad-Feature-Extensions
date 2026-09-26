"""本机运行机内装载核心的故障模型，并核对实际 C++ 重定位结果。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=MODULE.parents[3]

def main():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    out=MODULE/'build/boot-model';out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    for key,folder in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
        p=out/folder;p.mkdir(exist_ok=True);env[key]=str(p)
    sources=[MODULE/'native/boot_loader.cpp',MODULE/'native/boot_loader.h',HERE/'boot_loader.test.cpp',Path(__file__),
        MODULE/'build/boot-data/boot_contract_data.h',MODULE/'build/boot-data/af_relocation_data.h']
    hashes={str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    exe=out/'boot_loader_check.exe'
    cmd=[str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'c++','-std=c++11','-O2','-Wall','-Wextra','-Werror',
         str(MODULE/'native/boot_loader.cpp'),str(HERE/'boot_loader.test.cpp'),'-o',str(exe)]
    subprocess.run(cmd,cwd=ROOT,env=env,check=True)
    completed=subprocess.run([str(exe)],cwd=ROOT,env=env,text=True,capture_output=True)
    print(completed.stdout,end='');print(completed.stderr,end='');completed.check_returncode()
    for base in (0x2bace0,0x39cec0,0x6b2c80):
        target=out/f'relocated-{base:08x}.bin'
        subprocess.run([str(exe),'relocate',hex(base),str(target)],cwd=ROOT,env=env,check=True)
        reference=MODULE/f'build/boot-data/build/release/{base:08x}/candidate.bin'
        if target.read_bytes()!=reference.read_bytes():raise RuntimeError('C++ relocation differs from independent link')
    if hashes!={str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:raise RuntimeError('sources changed')
    report={'passed':True,'hardwareRequests':0,'installed':False,'sources':hashes,'model':completed.stdout.strip(),'cppIndependentLinksMatched':3}
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
