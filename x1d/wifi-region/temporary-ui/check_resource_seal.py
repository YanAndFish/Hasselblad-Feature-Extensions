"""封装篡改拒绝、完整资源恢复和 Qt 内存注册；不连接相机。"""
from pathlib import Path
import ctypes
import hashlib
import json
import sys
import time
P=Path(__file__).resolve().parent;R=P.parents[2]
sys.dont_write_bytecode=True
sys.path[:0]=[str(P),str(R/'x1d/patch-distribution'),str(R/'x1d/wireless-flash/build/ui-test-python')]
from seal_resources import host_library,seal,unseal,current_key_id
from build_viewfinder_modes import read_rcc
from PySide6.QtCore import QResource,QFile,QIODevice

plain=(P/'build/flash-ui.rcc').read_bytes()
lib=host_library(current_key_id())
sealed=seal(plain,lib)
assert sealed[:8]==b'HBLRSC01' and len(sealed)==len(plain)+48
start=time.perf_counter()
restored=unseal(sealed,lib)
host_seconds=time.perf_counter()-start
assert restored==plain
rejected=0
for offset in [0,9,31,32,len(sealed)//2,len(sealed)-17,len(sealed)-1]:
    changed=bytearray(sealed);changed[offset]^=1
    try:unseal(bytes(changed),lib)
    except ValueError:rejected+=1
    else:raise AssertionError('Tampered resource accepted')
for size in [0,7,31,47,48,len(sealed)-1]:
    try:unseal(sealed[:size],lib)
    except ValueError:rejected+=1
    else:raise AssertionError('Truncated resource accepted')
assert seal(plain,lib)!=sealed, 'Fresh encryption must use a fresh nonce'
out=ctypes.create_string_buffer(len(plain)-1)
assert lib.hbl_resource_open(out,len(out),sealed,len(sealed))==0
assert b'import QtQuick' not in sealed and b'FocusDelivery' not in sealed
assert QResource.registerResourceData(restored)
resources=read_rcc(plain)
for name,value in resources.items():
    f=QFile(':'+name);assert f.open(QIODevice.ReadOnly),name
    assert bytes(f.readAll())==value.encode('utf-8'),name
    f.close()
    del f
assert QResource.unregisterResourceData(restored)
output=P/'build/resource-seal-test';output.mkdir(parents=True,exist_ok=True)
(output/'sealed.rcc').write_bytes(sealed)
report=dict(passed=True,resourcesVerified=len(resources),tamperOrTruncationRejected=rejected,undersizedOutputRejected=True,
            inMemoryRegistrationVerified=True,hardwareRequests=0,qtHostVersion=6,armQt5RuntimeVerified=False,
            hostDecryptSeconds=host_seconds,performanceNote='电脑单次解封时间，非相机启动或操作延迟',
            plaintextSha256=hashlib.sha256(plain).hexdigest(),sealedSha256=hashlib.sha256(sealed).hexdigest(),
            limitation='原生加载器内仍有解密密钥；无管理员动态提取抵抗或逆向最低耗时承诺')
(output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if 'Sha256' not in k},ensure_ascii=False))
