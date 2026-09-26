"""独立 Qt 资源读取验证；不依赖组合器自己的解码实现。"""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QResource,QFile,QIODevice,qVersion
p=HERE/'build/combined-ui.rcc'
report=json.loads((HERE/'build/resources.json').read_text())
assert QResource.registerResource(str(p),'/four-module-test')
try:
    for name,value in report['resources'].items():
        f=QFile(':/four-module-test'+name)
        assert f.open(QIODevice.ReadOnly),name
        data=bytes(f.readAll());f.close();del f
        assert hashlib.sha256(data).hexdigest()==value['sha256'],name
finally:assert QResource.unregisterResource(str(p),'/four-module-test')
proof={'passed':True,'resources':len(report['resources']),'qtVersion':qVersion(),'rccSha256':report['rccSha256'],'hardwareRequests':0}
(HERE/'CodeTests/qt-resource-validation.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
