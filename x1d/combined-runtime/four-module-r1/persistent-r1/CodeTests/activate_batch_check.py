"""本机运行机内装载核心的故障模型，并核对实际 C++ 重定位结果。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=MODULE.parents[3]

def main():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    out=MODULE/'build/activate-boot';out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    for key,folder in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
        p=MODULE/'build/controller-first'/folder;p.mkdir(exist_ok=True);env[key]=str(p)
    sources=[MODULE/'build/activate-boot/seed_data.h',MODULE/'build/activate-boot/seed.bin',MODULE/'native/boot_activate_seed.c',MODULE/'build/task-cache/image.h',MODULE/'native/af_task_cache_init.c',MODULE/'build/task-cache/early_data.h',MODULE/'build_controller_first_loader.py',MODULE/'native/boot_task_cache_adapter.c',MODULE/'build/task-cache/staged_adapter.bin',MODULE/'build/activate-boot/activate_loader.cpp',MODULE/'native/boot_loader.h',HERE/'activate_batch.test.cpp',HERE/'boot_loader.test.cpp',MODULE/'build/batch-model/adapter_data.h',MODULE/'native/boot_batch.h',MODULE/'build/task-cache/boot_batch_wire.h',MODULE/'build/task-cache/boot_batch_mailbox.h',MODULE/'build/task-cache/boot_batch_envelope.h',Path(__file__),
        MODULE/'build/boot-data/boot_contract_data.h',MODULE/'build/boot-data/af_relocation_data.h']
    hashes={str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    exe=out/'production_check.exe'
    cmd=[str(ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'),'c++','-std=c++11','-O2','-Wall','-Wextra','-Werror',
         str(MODULE/'build/activate-boot/activate_loader.cpp'),str(HERE/'activate_batch.test.cpp'),'-o',str(exe)]
    subprocess.run(cmd,cwd=ROOT,env=env,check=True)
    completed=subprocess.run([str(exe)],cwd=ROOT,env=env,text=True,capture_output=True)
    print(completed.stdout,end='');print(completed.stderr,end='');completed.check_returncode()
    if hashes!={str(p.relative_to(MODULE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:raise RuntimeError('sources changed')
    report={'passed':True,'hardwareRequests':0,'installed':False,'sources':hashes,'model':completed.stdout.strip(),'afOnly':True,'timingProven':False,'transportImplemented':False}
    (out/'lifecycle-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
