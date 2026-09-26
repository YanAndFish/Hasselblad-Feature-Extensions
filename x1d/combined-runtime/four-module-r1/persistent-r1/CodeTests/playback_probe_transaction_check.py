"""只读探针更新的失败回退验证，无硬件操作。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=(HERE/'bus_ready_repair_check.py').read_text(encoding='utf-8')
s=s.replace("FILES=['farm.conf','baseline.sha256','manifest.sha256']","FILES=['radio.bin','baseline.sha256','manifest.sha256']")
s=s.replace("ADDED=['bus-ready.sh']","ADDED=[]")
s=s.replace("WORK/'repair-bus-ready.sh'","WORK/'build/playback-probe/install-stage/repair.sh'")
s=s.replace('*/farm.conf.batch-next','*/radio.bin.batch-next')
s='\n'.join(line for line in s.splitlines() if not line.strip().startswith("assert (root/'etc/systemd"))+'\n'
s=s.replace('build/bus-ready/transaction-validation.json','build/playback-probe/transaction-validation.json')
exec(compile(s,str(HERE/'bus_ready_repair_check.py'),'exec'))
