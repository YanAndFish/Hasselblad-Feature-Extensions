"""上传已经离线验证的整包候选，不执行安装。"""
from pathlib import Path
P=Path(__file__).resolve().parent
s=(P/'stage_halfpress.py').read_text(encoding='utf-8')
s=s.replace("build/halfpress-ui","build/batch-radio").replace('/tmp/hbl-halfpress-b2','/tmp/hbl-batch-radio-b1').replace("Lines('halfpress-upload')","Lines('batch-radio-upload')")
exec(compile(s,str(P/'stage_halfpress.py'),'exec'))
