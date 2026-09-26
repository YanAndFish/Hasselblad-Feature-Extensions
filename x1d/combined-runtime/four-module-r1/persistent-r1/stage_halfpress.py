"""仅上传校验已验证的半按候选；不运行安装脚本。"""
from pathlib import Path
import sys,json,hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;O=P/'build/halfpress-ui'
sys.path.insert(0,str(P.parent));import session
proof=json.loads((O/'transaction-validation.json').read_text())
assert proof['passed'] and proof['scriptSha256']==hashlib.sha256((O/'install-stage/repair.sh').read_bytes()).hexdigest()
report=json.loads((O/'package.json').read_text())
class Lines(session.Session):
    def command(self,label,command,timeout_ms=15000):
        if label.startswith('chunk-'):command=command.replace('printf %s ',"printf '%s\\n' ",1)
        return super().command(label,command,timeout_ms)
session.transport.REMOTE='/tmp/hbl-halfpress-b2'
s=Lines('halfpress-upload')
try:
    result=session.transport.stage(s,report,(O/'install.tgz').read_bytes())
    (O/'staging.json').write_text(json.dumps(dict(result=result,session=s.summary()),indent=2),encoding='utf-8')
    print(json.dumps(result))
finally:print(json.dumps(s.summary()))
