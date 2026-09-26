"""现装完整自有AF的固定只读诊断；不触发AF，不清状态，无任意地址入口。"""
import sys,json,struct,hashlib
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
import full_loader as F
L=F.L
NATIVE=(0x6bb46c,0x6bb598,0x6bb59c,0x6bb5a0,0x6bb5a4,0x6bb5b4,
        0x6bc954,0x6bc958,0x6bc95c,0x6bc960,0x6bc964,0x6bc980,0x6bc984,0x6bc994,0x6bc998,
        0x6cc59c,0x6cc5a0,0x6bcb44,0x2adc78,0x2adc8c,0x6badd0)
L.WRITE_SET=set()
L.READ_SET=set(NATIVE)|{L.CB,L.ARG}|set(range(F.STATE,F.STATE+F.M['stateBytes'],4))|{a for a,_,_ in F.M['hooks']+F.M['speed_words']}
NAMES=('magic abi armed until generation phase reason calls reversals confirmations owned started leg_started seen waiting_reset skip samples up down '
       'direction command origin last_position best_index best_cv noise roi0 roi1 rate configured pending_error '
       'fine_start fine_end coarse_peak target command_target move_started reply_seen reply_status reply_tick corrections position_tolerance physical '
       'position_tick position_seq raw_cv raw_tick raw_seq verify_seq verify_points stopped_tick position_baseline blocked_commands send_returns trace_count trace_overflow').split()
SIGNED=set('direction command origin last_position best_index fine_start fine_end coarse_peak target command_target physical'.split())
def decode(raw):
    values={n:struct.unpack_from('<i' if n in SIGNED else '<I',raw,4*i)[0] for i,n in enumerate(NAMES)}
    off=len(NAMES)*4
    values['samplesData']=[dict(position=struct.unpack_from('<i',raw,off+4*i)[0],cv=struct.unpack_from('<I',raw,off+256+4*i)[0]) for i in range(min(values['samples'],64))]
    off+=512
    values['trace']=[dict(zip(('tick','phase','command','position','cv'),struct.unpack_from('<IIiiI',raw,off+20*i))) for i in range(min(values['trace_count'],12))]
    values['canary']=struct.unpack_from('<I',raw,len(raw)-4)[0]
    return values
def main():
    assert Path.cwd().resolve()==L.ROOT.resolve()
    io=L.FixedIO(limit=350);result={'at':datetime.now().astimezone().isoformat(),'payloadSha256':F.M['payload_sha256'],'readOnly':True}
    try:
        io.exchange('version')
        if io.read(0x6bb46c)&255:raise RuntimeError('AF not idle')
        for a,_,expected in F.M['hooks']+F.M['speed_words']:
            if io.read(a)!=expected:raise RuntimeError('installed hook/speed mismatch '+hex(a))
        if io.read(L.CB)!=L.ORIG_CB or io.read(L.ARG)!=L.ORIG_ARG:raise RuntimeError('callback mismatch')
        initial=[io.read(F.STATE+i) for i in (0,4,8,16,F.M['canaryOffset'])]
        if initial[:3]!=[F.M['stateMagic'],2,2] or initial[-1]!=F.M['canary']:raise RuntimeError('state guard mismatch')
        raw=b''.join(struct.pack('<I',io.read(a)) for a in range(F.STATE,F.STATE+F.M['stateBytes'],4))
        result['state']=decode(raw);result['native']={hex(a):io.read(a) for a in NATIVE}
        if io.read(F.STATE+16)!=initial[3] or io.read(0x6bb46c)&255:raise RuntimeError('AF changed during snapshot')
        result['completed']=True
    finally:
        result.update(requests=io.requests,writes=io.writes,allHandlesClosed=io.closed)
        path=L.HERE/'recovery'/('full-diagnostic-'+datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')+'.json')
        if path.exists():raise RuntimeError('diagnostic filename exists')
        path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2));print(path.name)
if __name__=='__main__':main()
