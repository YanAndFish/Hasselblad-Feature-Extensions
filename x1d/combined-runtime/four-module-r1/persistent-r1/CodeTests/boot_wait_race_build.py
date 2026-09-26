"""编译目标Linux原子替换竞争复现器；编译阶段没有设备请求。"""
from pathlib import Path
import os,subprocess,hashlib,json
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
assert Path.cwd().resolve()==ROOT
out=P/'build/fast-start-research'
units=[]
for kind,src in [('old',out/'boot_wait_before_race.c'),('fixed',P/'native/boot_wait.c')]:
    text='#define _GNU_SOURCE\n#include <sys/stat.h>\n#include <unistd.h>\nstatic const char *race_path;\nstatic int race_fstat(int fd,struct stat *st) { if(race_path) {unlink(race_path);race_path=0;}return fstat(fd,st); }\n#define fstat race_fstat\n#define main hidden_'+kind+'_main\n#include "'+src.as_posix()+'"\n#undef main\n#undef fstat\n'
    text+='int '+kind+'_race(void) {char d[]="/tmp/hbl-race-XXXXXX",p[128];if(!mkdtemp(d))return -99;snprintf(p,sizeof(p),"%s/state",d);if(!put(p,"ready"))return -98;int fd=open(d,O_DIRECTORY|O_RDONLY);race_path=p;int r=state(fd,"state","ready",0);close(fd);unlink(p);rmdir(d);return r;}\n'
    if kind=='fixed':text+='extern int old_race(void);\nint main(void) {int a=old_race(),b=fixed_race();printf("atomic-replace old=%d fixed=%d expected=-1,0 hardware=0\\n",a,b);return a==-1 && b==0 ? selftest():93;}\n'
    path=out/('race_'+kind+'.c');path.write_text(text,encoding='utf-8');units.append(str(path))
env=dict(os.environ)
for k,n in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
 d=out/n;d.mkdir(exist_ok=True);env[k]=str(d)
zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
subprocess.run([str(zig),'cc','-target','arm-linux-musleabihf','-mcpu=cortex_a9','-Os','-static','-s','-Wall','-Wextra','-Werror',*units,'-o',str(out/'boot-wait-race')],env=env,check=True)
print('built offline race reproducer')
