"""复用固定文件事务故障注入，检验 UI/worker 成对恢复。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=(HERE/'bus_ready_repair_check.py').read_text(encoding='utf-8')
s=s.replace("FILES=['farm.conf','baseline.sha256','manifest.sha256']","FILES=['libhbl-af-loader.so','libhbl-af-ui.so','baseline.sha256','manifest.sha256']")
s=s.replace("ADDED=['bus-ready.sh']","ADDED=[]")
s=s.replace("WORK/'repair-bus-ready.sh'","WORK/'build/halfpress-ui/install-stage/repair.sh'")
s=s.replace('*/farm.conf.batch-next','*/libhbl-af-ui.so.batch-next')
s='\n'.join(line for line in s.splitlines() if not line.strip().startswith("assert (root/'etc/systemd"))+'\n'
s=s.replace('build/bus-ready/transaction-validation.json','build/halfpress-ui/transaction-validation.json')
exec(compile(s,str(HERE/'bus_ready_repair_check.py'),'exec'))
