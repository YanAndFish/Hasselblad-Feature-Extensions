"""仅离线构建固定网络候选与 Windows mock；不执行 ARM 或任何网络工具。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUTPUT=HERE/'build'
BASE=ROOT/'.research-cache/x1d-1.25.0'

def main():
    assert Path.cwd().resolve()==ROOT
    OUTPUT.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    for name,folder in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
        p=OUTPUT/folder;p.mkdir(exist_ok=True);env[name]=str(p)
    zig=BASE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    common=['-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-O2']
    def run(args):
        result=subprocess.run([str(zig),'cc']+args,env=env,capture_output=True,text=True,timeout=120)
        if result.returncode:raise RuntimeError(result.stderr)
    run(common+[str(HERE/'network_core.c'),str(HERE/'CodeTests/network_core_test.c'),'-o',str(OUTPUT/'network-core-test.exe')])
    test=subprocess.run([str(OUTPUT/'network-core-test.exe')],capture_output=True,text=True,timeout=20)
    if test.returncode:raise RuntimeError(test.stderr+test.stdout)
    results=json.loads(test.stdout)
    (OUTPUT/'mock-result.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    for name,defines in [('network-native',[]),('dhcp-native',['-DHBL_DHCP_MAIN=1'])]:
        run(common+['-target','arm-linux-musleabihf','-mcpu=cortex_a9','-static','-fno-ident','-fvisibility=hidden','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-Wl,-s']+defines+[str(HERE/'network_core.c'),str(HERE/'network_posix.c'),'-o',str(OUTPUT/name)])
        binary=(OUTPUT/name).read_bytes()
        assert binary[:7]==b'\x7fELF\x01\x01\x01' and int.from_bytes(binary[18:20],'little')==40
        # No PT_INTERP: both artifacts are self-contained static ARM executables.
        offset=int.from_bytes(binary[28:32],'little');size=int.from_bytes(binary[42:44],'little');count=int.from_bytes(binary[44:46],'little')
        assert all(int.from_bytes(binary[offset+n*size:offset+n*size+4],'little')!=3 for n in range(count))
    sources=[HERE/'network_core.h',HERE/'network_core.c',HERE/'network_posix.c',HERE/'CodeTests/network_core_test.c',Path(__file__).resolve(),HERE.parent/'network.sh',HERE.parent/'build/dhcp.sh',HERE.parent/'radio-mode.sh',HERE.parent/'entry.cpp',BASE/'rootfs-inventory.json']
    report={'built':True,'installed':False,'armExecuted':False,'networkOperations':0,'mock':results,
        'target':'arm-linux-musleabihf / cortex-a9 / static ELF32 ARM','files':{},'sources':{}}
    for name in ['network-native','dhcp-native','network-core-test.exe','mock-result.json']:
        p=OUTPUT/name;report['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
    for p in sources:report['sources'][p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    (OUTPUT/'build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**results,'armBuilt':True,'armExecuted':False,'installed':False}))

if __name__=='__main__':main()
