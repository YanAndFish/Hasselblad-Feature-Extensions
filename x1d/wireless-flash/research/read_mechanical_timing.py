"""只读取本模块的关闭后记录；不接触照片，不发试闪或快门请求。"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from analyze_mechanical_timing import parse, analyze, to_csv

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / 'build/mechanical-timing-candidate'

def read(session):
    # 由用户先关闭自动引闪；只有关闭且无线空闲时 worker 才保存此文件。
    probe = session.command('timing-file-size', 'd=/tmp/hbl-wireless-flash; test -f "$d/timing.bin" && wc -c < "$d/timing.bin"')
    size = int(probe['output'].strip())
    if not 32 <= size <= 147488 or (size-32) % 72:
        raise RuntimeError('Invalid timing file size')
    before = session.command('timing-file-hash-before', 'sha256sum /tmp/hbl-wireless-flash/timing.bin')['output'].split()[0]
    if not re.fullmatch('[0-9a-f]{64}', before):
        raise RuntimeError('Invalid timing hash')
    data = bytearray()
    for index in range((size+95)//96):
        expected = min(96, size-len(data))
        command = ('/usr/bin/hexdump -v -s ' + str(index*96) + ' -n ' + str(expected) +
                   ' -e \'1/1 "%02x"\' /tmp/hbl-wireless-flash/timing.bin')
        output = session.command('timing-bytes-' + str(index), command)['output']
        if not re.fullmatch('[0-9a-f]{' + str(expected*2) + '}', output):
            raise RuntimeError('Invalid timing chunk; do not retry automatically')
        data.extend(bytes.fromhex(output))
        if (index+1) % 100 == 0:
            print('timing chunks read', index+1, '/', (size+95)//96, flush=True)
    after = session.command('timing-file-hash-after', 'sha256sum /tmp/hbl-wireless-flash/timing.bin')['output'].split()[0]
    if before != after or hashlib.sha256(data).hexdigest() != before:
        raise RuntimeError('Timing file changed during read; no analysis accepted')
    record = parse(data)
    result = analyze(record)
    folder = OUT / ('capture-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir()
    (folder/'timing.bin').write_bytes(data)
    (folder/'timing.csv').write_text(to_csv(record), encoding='utf-8-sig', newline='')
    result.update(targetFileSha256=before, bytes=len(data),
                  evidence=str(session.output.relative_to(HERE)),
                  allHandlesClosed=all(e['matched'] and e['closed'] for e in session.entries),
                  cameraShotsTriggered=0, agentFlashTrials=0)
    (folder/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return folder, result
