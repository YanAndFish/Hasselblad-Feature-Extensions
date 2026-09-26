"""Decode only scan-speed writes to the lens bridge, never received photo data."""
import argparse
import json
import re
from pathlib import Path

# X2D 4.2.0: librcam _SendCDFocusRequest -> command 0x1b, subtype 5.
# librcam queue frame is 40 bytes; duss_hal_x2bridge_write writes it unchanged.
WRITE = re.compile(r'write\(\d+(?:<[^>]*>)?, "((?:\\x[0-9a-fA-F]{2})*)", (\d+)\)\s*=\s*(-?\d+)')

def summarize(text):
    sent=[];failed=0;partial=0;other=0;unparsed=0;pending={}
    for line in text.splitlines():
        # strace -f may split concurrent calls. Join using the recorded TID.
        prefix=re.match(r'^(?:\[pid\s+)?(\d+)(?:\])?\s+(.*)$',line)
        tid,body=(prefix.group(1),prefix.group(2)) if prefix else ('single',line)
        if '<unfinished ...>' in body and 'write(' in body:
            if tid in pending:unparsed+=1
            pending[tid]=body.replace('<unfinished ...>','').rstrip();continue
        if '<... write resumed>' in body:
            if tid not in pending:unparsed+=1;continue
            line=pending.pop(tid)+body.split('<... write resumed>',1)[1]
        m=WRITE.search(line)
        if not m:
            if 'write(' in line:unparsed+=1
            continue
        data=bytes.fromhex(m.group(1).replace('\\x',''))
        requested,returned=map(int,m.group(2,3))
        if returned<0:failed+=1;continue
        if returned!=requested or len(data)!=requested:partial+=1;continue
        if len(data)!=40 or data[:4]!=b'\x0a\xf8\0\0' or data[4:8]!=b'\x1b\0\0\0':
            other+=1;continue
        if data[8]!=5:
            other+=1;continue  # subtype 6/10 values are positions, not speed!
        speed=int.from_bytes(data[9:11],'big',signed=True)
        sent.append(speed)
    unparsed+=len(pending)
    complete=partial==0 and unparsed==0 and not any(x in text for x in ['File size limit exceeded','Operation not permitted','Permission denied'])
    return dict(scope='kernel-accepted /dev/lens scan-speed write; not measured motor velocity or lens acknowledgement',
                scanCommands=len(sent),positiveMaximum=max((x for x in sent if x>=0),default=None),
                absoluteMaximum=max(map(abs,sent),default=None),negativeMinimum=min((x for x in sent if x<0),default=None),
                failedWrites=failed,partialWrites=partial,otherCommands=other,unparsedWrites=unparsed,
                parseComplete=complete,actualScanMaximum= max(map(abs,sent)) if complete and sent else None)

def self_test():
    def frame(speed,subtype=5,ret=40):
        b=bytearray(40);b[:2]=b'\x0a\xf8';b[4]=0x1b;b[8]=subtype;b[9:11]=speed.to_bytes(2,'big',signed=True)
        return '421 write(31, "'+''.join('\\x%02x'%x for x in b)+'", 40) = '+str(ret)
    r=summarize('\n'.join([frame(5170),frame(-7755),frame(30000,6),frame(31000,10),frame(9000,ret=-1)]))
    assert r['actualScanMaximum']==7755 and r['scanCommands']==2 and r['failedWrites']==1
    assert summarize(frame(7755,ret=20))['actualScanMaximum'] is None
    assert summarize('421 write(31, "\\x0a"..., 40) = 40')['parseComplete'] is False
    assert summarize('')['actualScanMaximum'] is None
    line=frame(7755);left,right=line.split(') = ')
    split=left+' <unfinished ...>\n421 <... write resumed>) = '+right
    assert summarize(split)['actualScanMaximum']==7755
    assert summarize('421 <... write resumed>) = 40')['parseComplete'] is False
    return 'PASS: signed speeds, exact frame, return count, truncated/interleaved trace, position exclusion, empty capture'

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('trace',nargs='?');ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
    if a.self_test:print(self_test())
    elif a.trace:print(json.dumps(summarize(Path(a.trace).read_text(encoding='utf-8-sig')),indent=2))
    else:ap.error('trace path or --self-test required')
