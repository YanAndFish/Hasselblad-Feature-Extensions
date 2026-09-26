"""本地资源封装与同源解封验证。构建密钥、主机测试库均不进入发行目录。"""
from pathlib import Path
import ctypes
import os
import subprocess
import shutil
import sys
import json
import re

P=Path(__file__).resolve().parent
R=P.parents[2]
ZIG=R/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
PRIVATE=R/'.app-data/patch-licensing/resource-seal-key.bin'

def current_key_id():
    metadata=P/'build/build.json'
    return json.loads(metadata.read_text()).get('resourceSealId') if metadata.exists() else None

def key_path(key_id):
    if key_id is None:return PRIVATE
    if not re.fullmatch('[0-9a-f]{32}',key_id):raise ValueError('Invalid resource sealing revision')
    return PRIVATE.parent/'resource-seal'/(key_id+'.bin')

def build(host=False,key_id=None,create=False):
    private=key_path(key_id)
    private.parent.mkdir(parents=True,exist_ok=True)
    if not private.exists():
        if not create:raise ValueError('Resource sealing key is unavailable')
        fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(os.urandom(32))
    key=private.read_bytes()
    if len(key)!=32:raise ValueError('Resource sealing key has invalid size')
    target=P/'build/resource-seal'/(key_id or 'legacy')/('host' if host else 'arm')
    target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(P/'resource_seal.zig',target/'resource_seal.zig')
    (target/'resource_seal_config.zig').write_text('pub const pack_enabled='+str(host).lower()+';\npub const key:[32]u8=.{'+','.join(map(str,key))+'};\n')
    output=target/('resource-seal.dll' if host else 'resource-seal.a')
    args=[str(ZIG),'build-lib',str(target/'resource_seal.zig'),'-O','ReleaseSafe','-fstrip','-femit-bin='+str(output),
          '--cache-dir',str(R/'.research-cache/x1d-1.25.0/zig-local-cache'),'--global-cache-dir',str(R/'.research-cache/x1d-1.25.0/zig-global-cache')]
    if host:args+=['-dynamic']
    else:args+=['-target','arm-linux-gnueabihf.2.22','-mcpu','cortex_a9','-lc','-fPIC']
    subprocess.run(args,check=True)
    return output

def host_library(key_id=None):
    lib=ctypes.CDLL(str(build(True,key_id)))
    lib.hbl_resource_open.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
    lib.hbl_resource_open.restype=ctypes.c_int
    lib.hbl_resource_pack.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
    lib.hbl_resource_pack.restype=ctypes.c_int
    return lib

def seal(plain,lib=None):
    lib=lib or host_library(current_key_id())
    out=ctypes.create_string_buffer(len(plain)+48)
    size=lib.hbl_resource_pack(out,len(out),plain,len(plain),os.urandom(24))
    if size!=len(out):raise ValueError('Resource seal failed')
    return out.raw

def unseal(sealed,lib=None):
    lib=lib or host_library(current_key_id())
    if len(sealed)<48:raise ValueError('Resource seal is truncated')
    out=ctypes.create_string_buffer(len(sealed)-48)
    size=lib.hbl_resource_open(out,len(out),sealed,len(sealed))
    if size<=0:raise ValueError('Resource authentication failed')
    return out.raw[:size]

def package_resource(source,destination):
    lib=host_library(current_key_id())
    plain=Path(source).read_bytes()
    sealed=seal(plain,lib)
    if unseal(sealed,lib)!=plain:raise ValueError('Resource round trip failed')
    Path(destination).write_bytes(sealed)

if __name__=='__main__':
    package_resource(sys.argv[1],sys.argv[2])
    print('Sealed resource round trip verified; no camera access')
