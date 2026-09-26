"""只读核对本轮已验收 AF，供组合安装保留其现有 RAM；默认离线。"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
AF=ROOT/'x1d/af-experiment'
R7=AF/'camera-settings-r1/delivery-r7'
sys.path[:0]=[str(R7),str(R7.parent),str(AF),str(ROOT/'x1d/tools')]
import runtime
from native_install import NativeContract
from r3_install_journal import InstallJournal
FIXED='bc73f1f2a2527efca6f1c22445258d4133bb80ae18103e220eefdcf8437668cb'
SOURCE=R7/'recovery/temporary-release-20260914-020151.json'


def source():
    header=json.loads(SOURCE.read_text(encoding='utf-8'))
    record=InstallJournal.read_record(SOURCE,header['artifactSha256'])
    if not record.get('installed') or not record.get('allHandlesClosed') or record.get('inFlight') or record.get('cacheInFlight') or record['journalAudit']['incompleteTail']:
        raise ValueError('AF installation record incomplete')
    m=record['candidate'];blob=(R7/'build/release'/f"{m['base']:08x}"/'candidate.bin').read_bytes()
    if hashlib.sha256(blob).hexdigest()!=FIXED or m['payload_sha256']!=FIXED:
        raise ValueError('accepted AF payload changed')
    expected={a:new for a,_,new in m['emulatorOnlyHooks']}
    expected.update({m['base']+i:struct.unpack_from('<I',blob,i)[0] for i in range(0,m['state_start']-m['base'],4)})
    expected[m['symbols']['af_install_ack']]=runtime.old.EXEC_MAGIC
    expected[runtime.old.CB]=runtime.old.ORIG_CB
    expected[runtime.old.ARG]=runtime.old.ORIG_ARG
    return record,m,expected


class ReadOnly:
    count=-1
    def __init__(self,expected):
        self.reads=set(expected)|{0x6bb46c,0x6bb598}
        self.identity=hashlib.sha256(json.dumps(sorted(expected.items())).encode()).hexdigest()
    def packet(self,kind,a=None,v=None,size=512):
        if kind!='read':raise ValueError('only fixed memory reads allowed')
        return NativeContract.packet(self,kind,a,v,size)
    reply=staticmethod(NativeContract.reply)


def run(live=False):
    record,m,expected=source();c=ReadOnly(expected)
    for a in c.reads:
        if len(c.packet('read',a))!=512:raise ValueError('packet length')
    for kind,a,v in [('write',next(iter(c.reads)),0),('read',0,None),('read',1,None),('version',None,None)]:
        try:c.packet(kind,a,v)
        except ValueError:pass
        else:raise ValueError('read-only contract did not deny')
    if not live:return {'offlinePassed':True,'reads':len(c.reads),'hardwareRequests':0}
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    out=HERE/'build/sessions';out.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    trace=runtime.Trace(out/('af-preserve-'+stamp+'.trace.jsonl'),c.identity)
    io=runtime.TracedIO(c,trace)
    result={'passed':False,'afPayloadSha256':FIXED,'sourceInstallation':SOURCE.relative_to(ROOT).as_posix(),'hardwareRequests':0}
    try:
        for a,_,new in m['emulatorOnlyHooks']:
            if io.read(a)!=new:raise RuntimeError('current AF does not match accepted installation')
        for a,value in sorted(expected.items()):
            if io.read(a)!=value:raise RuntimeError('AF code, execution acknowledgement or callback differs')
        if io.read(0x6bb46c)&255 or io.read(0x6bb598)&255:raise RuntimeError('AF not idle')
        result['passed']=True
    finally:
        result.update(hardwareRequests=io.requests,writeRequests=io.writes,allHandlesClosed=io.closed,failed=io.failed)
        trace.close()
        (out/('af-preserve-'+stamp+'.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--read-current',action='store_true')
    print(json.dumps(run(p.parse_args().read_current)))
