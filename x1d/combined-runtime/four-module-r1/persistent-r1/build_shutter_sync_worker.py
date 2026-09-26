"""构建全按仅准备短引闪波形的 worker；保留当前无线固件和 UI。"""
from pathlib import Path
P=Path(__file__).resolve().parent
s=(P/'build_halfpress_worker.py').read_text(encoding='utf-8')
s=s.replace('build/halfpress-ui/worker','build/shutter-sync/worker')
exec(compile(s,str(P/'build_halfpress_worker.py'),'exec'))
