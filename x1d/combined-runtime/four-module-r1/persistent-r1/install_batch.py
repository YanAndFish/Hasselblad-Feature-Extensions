"""执行已核验整包事务，不重启相机或服务。"""
from pathlib import Path
P=Path(__file__).resolve().parent
s=(P/'install_halfpress.py').read_text(encoding='utf-8')
s=s.replace("build/halfpress-ui","build/batch-radio").replace('/tmp/hbl-halfpress-b2','/tmp/hbl-batch-radio-b1').replace("Session('halfpress-install')","Session('batch-radio-install')")
exec(compile(s,str(P/'install_halfpress.py'),'exec'))
