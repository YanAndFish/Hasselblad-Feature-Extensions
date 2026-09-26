"""Compile a device-API-free Qt 5.5 lifecycle check using the existing ABI."""
from pathlib import Path
import os, subprocess
P=Path(__file__).resolve().parent
R=P.parents[2]
C=R/'.research-cache/x1d-1.25.0'
B=C/'baseline'
O=P/'build/jpeg-probe'
O.mkdir(parents=True,exist_ok=True)
env=dict(os.environ)
for key,name in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
    d=O/name;d.mkdir(exist_ok=True);env[key]=str(d)
qt=C/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
zig=C/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
flags=target+['-I',str(base/'src/3rdparty/angle/include'),'-marm','-O2','-fPIC','-fno-stack-protector','-I',str(P/'build/include'),'-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion']
libs=[B/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ['Quick','Qml','Gui','Network','Core']]+[B/n for n in ['usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so']]
obj=O/'probe.o'
commands=[['c++','-std=c++11']+flags+['-DHBL_JPEG_PROBE','-c',str(P/'jpeg_provider.cpp'),'-o',str(obj)],['cc']+target+['-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(P/'build/relocations.ld'),str(obj),str(P/'build/jpeg_container.o')]+list(map(str,libs))+['-o',str(O/'jpeg-probe')]]
for command in commands:
    result=subprocess.run([str(zig)]+command,env=env,capture_output=True,text=True,timeout=90)
    if result.returncode:raise RuntimeError(result.stderr)
print('Built isolated Qt 5.5 JPEG probe; not run on camera')
