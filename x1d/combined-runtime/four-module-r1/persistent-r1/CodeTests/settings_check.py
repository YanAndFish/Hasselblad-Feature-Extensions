from pathlib import Path
import hashlib,json,os,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
OUT=HERE/'settings-output'
OUT.mkdir(exist_ok=True)
env=os.environ.copy()
for key,name in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
    p=OUT/name;p.mkdir(exist_ok=True);env[key]=str(p)
compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
exe=OUT/'settings-check.exe'
subprocess.run([str(compiler),'c++','-std=c++11','-O2','-Wall','-Wextra','-Werror',str(HERE/'persistent_settings.test.cpp'),'-o',str(exe)],env=env,check=True)
done=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
report={'passed':True,'output':done.stdout.strip(),'hardwareRequests':0,'sources':{str(p.relative_to(HERE.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'persistent_settings.test.cpp',HERE.parent/'native/persistent_settings.h']}}
(OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
