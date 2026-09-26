"""构建相机独立文件读取竞态夹具；不连接设备，不请求相机业务。"""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'x1d/combined-runtime/four-module-r1/persistent-r1'
OUT=ROOT/'x1d/patch-distribution/build/boot-hold-repair'
def main():
    assert Path.cwd().resolve()==ROOT
    OUT.mkdir(exist_ok=True)
    cc=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    base=ROOT/'.research-cache/x1d-1.25.0/baseline'
    commands=[['c++','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
       '-DHBL_HOLD_SHARED_TEST','-I'+str(P/'native'),'-c',str(ROOT/'CodeTests/boot_hold_race.cpp'),'-o',str(OUT/'hold-test.o')],
      ['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-shared','-Wl,--no-undefined','-Wl,-s',
       '-Wl,-T,'+str(P/'build/formal-flash-program/relocations.ld'),str(OUT/'hold-test.o'),
       str(base/'lib/libc-2.22.so'),str(base/'lib/libgcc_s.so.1'),'-o',str(OUT/'hold-test-fixed.so')]]
    for command in commands:subprocess.run([str(cc),*command],check=True)
    files=[ROOT/'CodeTests/boot_hold_race.cpp',P/'native/boot_hold_guard.h',P/'native/formal_install_hold.h',OUT/'hold-test-fixed.so']
    (OUT/'fixture-build.json').write_text(json.dumps(dict(commands=commands,
      sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}),indent=2),encoding='utf-8')
if __name__=='__main__':main()
