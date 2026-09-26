"""只读核对当前已授权 RAM 试用资源，不代替真实触控验收。"""
import hashlib
import json
import sys
from pathlib import Path

P = Path(__file__).resolve().parent
sys.path[:0] = [str(P.parents[1] / 'patch-distribution'), str(P.parents[1] / 'tools')]
from usb_transport import Channel

c = Channel()
with c.session():
    health = c.command('/run/hbl-hotspot-ui/health --require-ready;echo result:$?;true')
    mapped = c.command('p=$(cat /run/hbl-four-module/gui.pid);grep -c flash-ui.rcc /proc/$p/maps;true')
    errors = c.command('p=$(cat /run/hbl-four-module/gui.pid);journalctl _PID=$p -n 300 --no-pager -o cat | grep -E "TypeError|ReferenceError|Cannot assign|is not a type" | tail -c 230;true')
    digest = c.command('sha256sum /run/hbl-hotspot-ui/flash-ui.rcc')
    main_digest = c.command('sha256sum /run/hbl-hotspot-ui/Main.qml')
    entry_digest = c.command('sha256sum /run/hbl-hotspot-ui/libhotspot-entry.so')
evidence = P / 'build/ui-deployment.json'
r = json.loads(evidence.read_text()) if evidence.exists() else {}
features=json.loads((P/'build/deployed-features.json').read_text()) if (P/'build/deployed-features.json').exists() else {}
r.update({key:features[key] for key in ['newReplayEnabled','formatLockEnabled'] if key in features})
if features.get('entryDigest'):
    r['entryReadbackMatched']=features['entryDigest'] in entry_digest
r.update(resourceReadbackMatched=hashlib.sha256((P/'build/flash-ui.rcc').read_bytes()).hexdigest() in digest,
         hotspotPageReadbackMatched=hashlib.sha256((P/'Main.qml').read_bytes()).hexdigest() in main_digest,
         healthPassed='result:0' in health,
         resourceMapped=mapped.strip().isdigit() and int(mapped.strip()) > 0,
         qmlErrorsInCheckedRange=errors.strip(), physicalTouchVerified=False)
evidence.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
print(health)
print(json.dumps(r, ensure_ascii=False))
assert r['resourceReadbackMatched'] and r['hotspotPageReadbackMatched'] and r['healthPassed'] and r['resourceMapped'] and not r['qmlErrorsInCheckedRange']
if features.get('entryDigest'):assert r['entryReadbackMatched']
