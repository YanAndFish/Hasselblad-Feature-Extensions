"""完整批量无线更新的失败回退检查，无硬件请求。"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=(HERE/'bus_ready_repair_check.py').read_text(encoding='utf-8')
s=s.replace("FILES=['farm.conf','baseline.sha256','manifest.sha256']","FILES=['libhbl-af-loader.so','libhbl-af-ui.so','af-ui.rcc','radio.bin','prepare-radio.sh','baseline.sha256','manifest.sha256']")
s=s.replace("ADDED=['bus-ready.sh']","ADDED=[]")
s=s.replace("WORK/'repair-bus-ready.sh'","WORK/'build/batch-radio/install-stage/repair.sh'")
s=s.replace('*/farm.conf.batch-next','*/radio.bin.batch-next')
s='\n'.join(line for line in s.splitlines() if not line.strip().startswith("assert (root/'etc/systemd"))+'\n'
s=s.replace('build/bus-ready/transaction-validation.json','build/batch-radio/transaction-validation.json')
exec(compile(s,str(HERE/'bus_ready_repair_check.py'),'exec'))
