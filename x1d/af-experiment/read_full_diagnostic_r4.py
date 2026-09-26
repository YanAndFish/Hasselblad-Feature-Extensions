"""R4固定只读诊断。read才访问设备；不触发AF、不读安装唤醒计数、不写或清状态。"""
import sys,json,struct,argparse
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
import full_loader_r4 as L

NAMES=('magic abi armed boundary_hint generation phase reason calls reversals confirmations owned started leg_started seen waiting_reset skip samples up down '
       'direction command origin last_position best_index best_cv noise roi0 roi1 rate configured pending_error '
       'fine_start fine_end coarse_peak target command_target move_started reply_seen reply_status reply_tick corrections position_tolerance physical '
       'position_tick position_seq raw_cv raw_tick raw_seq verify_seq verify_points stopped_tick position_baseline blocked_commands send_returns trace_count trace_overflow').split()
SIGNED=set('direction command origin last_position best_index fine_start fine_end coarse_peak target command_target physical stable_position probe_origin video_command'.split())
TAIL1='stop_pending stable_tick stable_seq stable_points stable_position predictions brake_distance probe_active frame_seq frame_consumed'.split()
TAIL2='probe_origin refinements cv_profile video_state video_started video_raw video_fresh video_preview last_full_tick finish_pending video_command video_mipi canary'.split()
VNAMES='magic abi enabled session request ack target result applying dirty need_recovery external_epoch session_epoch request_epoch observed_width observed_height width height roi0 roi1 full_rate pipeline_calls pipeline_result spi_calls spi_result spi_bytes ready_tick ready_rate switches canary'.split()
PHASES='OFF WAIT_START PROBE ASCEND MOVE_START FINE_SCAN MOVE_PEAK VERIFY DONE FAILED'.split()
REASONS='OK CONFIG NO_DATA TIME_LIMIT TRAVEL_LIMIT WRONG_DIRECTION BAD_CV BAD_COUNT ENDPOINT LENS_ERROR POSITION_ERROR WEAK_PEAK CANCELLED BAD_STATE VIDEO_ERROR'.split()
NATIVE=(0x6bb46c,0x6bb598,0x2adc78,0x2adc8c,0x6badd0,0x6c176c,0x6c1778,0x6c172c)
AF=L.M['symbols']['af_state'];VIDEO=L.M['symbols']['fast_video_state'];LIMIT=400
GATE_STATUS=L.M['symbols']['fast_video_begin_status'];GATE_GENERATION=L.M['symbols']['fast_video_begin_generation']
GATE_REASONS={1:'此前切换尚未收尾',2:'160构件未启用',4:'需要恢复',8:'原厂AF状态不是3',
              16:'实时取景未活动',32:'实时取景不是mode5',64:'轮次无效',128:'尚无全幅尺寸',
              256:'数字增益大于1',512:'对焦框超出160有效区域',0x80000000:'尚未检查'}
ANCHORS=(AF+16,AF+20,AF+40,AF+176,AF+608,AF+820,VIDEO+12,VIDEO+16,VIDEO+20,VIDEO+32,VIDEO+112,GATE_GENERATION)

def decode(raw):
    if len(raw)!=860:raise ValueError('fixed ABI6 byte count')
    result={};off=0
    def fields(names):
        nonlocal off
        for name in names:
            result[name]=struct.unpack_from('<i' if name in SIGNED else '<I',raw,off)[0];off+=4
    fields(NAMES)
    positions=struct.unpack_from('<32h',raw,off);off+=64
    cvs=struct.unpack_from('<32I',raw,off);off+=128
    result['samplesData']=[{'position':positions[i],'cv':cvs[i]} for i in range(min(result['samples'],32))]
    result['trace']=[dict(zip(('tick','phase','command','position','cv'),struct.unpack_from('<IIiiI',raw,off+20*i))) for i in range(min(result['trace_count'],8))];off+=160
    fields(TAIL1)
    result['frames']=[dict(zip(('seq','tick','generation','cv','position','accepted_seq'),struct.unpack_from('<IIIIiI',raw,off+24*i))) for i in range(8)];off+=192
    fields(TAIL2)
    assert off==len(raw)
    result['phaseName']=PHASES[result['phase']] if result['phase']<len(PHASES) else 'UNKNOWN'
    result['reasonName']=REASONS[result['reason']] if result['reason']<len(REASONS) else 'UNKNOWN'
    return result

def read_set(contract):
    return set(range(AF,AF+860,4))|set(range(VIDEO,VIDEO+120,4))|set(NATIVE)|set(ANCHORS)|{
        L.CB,L.ARG,L.WAKE_HOOK,GATE_STATUS}|{a for a,_,_ in L.M['hooks']+L.M['speed_words']}

class ReadOnlyIO(L.FixedIO):
    def __init__(self,contract):
        super().__init__(contract);self.allowed_reads=read_set(contract)
        if not self.allowed_reads<=contract.reads:raise ValueError('read set outside reviewed contract')
        assert L.COUNT not in self.allowed_reads and L.SENT not in self.allowed_reads
    def exchange(self,kind,a=None,v=None):
        if self.requests>=LIMIT or kind not in ('version','read') or v is not None:
            raise ValueError('fixed read-only operation required')
        if kind=='read' and a not in self.allowed_reads:raise ValueError('fixed diagnostic address required')
        return super().exchange(kind,a,v)

def snapshot(io,result):
    io.exchange('version')
    mismatches=[]
    expected={a:new for a,old,new in L.M['hooks']+L.M['speed_words']}
    expected.update({L.CB:L.ORIG_CB,L.ARG:L.ORIG_ARG,L.WAKE_HOOK:io.contract.plan.wake_original})
    for a,v in expected.items():
        actual=io.read(a)
        if actual!=v:mismatches.append({'address':hex(a),'expected':v,'actual':actual})
    result['entryMismatches']=mismatches
    if mismatches:raise RuntimeError('installed entry mismatch; no state interpretation')
    before={a:io.read(a) for a in ANCHORS}
    raw=b''.join(struct.pack('<I',io.read(a)) for a in range(AF,AF+860,4))
    video=b''.join(struct.pack('<I',io.read(a)) for a in range(VIDEO,VIDEO+120,4))
    result['state']=s=decode(raw);result['video']=v=dict(zip(VNAMES,struct.unpack('<30I',video)))
    if (s['magic'],s['abi'],s['canary'])!=(L.M['stateMagic'],6,L.M['canary']):raise RuntimeError('AF ABI guard')
    if (v['magic'],v['abi'],v['canary'])!=(0x46313630,1,0x30363146):raise RuntimeError('video ABI guard')
    result['native']={hex(a):io.read(a) for a in NATIVE}
    reason=io.read(GATE_STATUS);generation=io.read(GATE_GENERATION)
    result['eligibility']={'generation':generation,'status':reason,
        'reasons':[label for bit,label in GATE_REASONS.items() if reason&bit],
        'matchesAfGeneration':generation==s['generation'] and generation!=0,
        'qualified':reason==0 and generation!=0}
    after={a:io.read(a) for a in ANCHORS}
    result['stableAnchors']=before==after
    result['changedAnchors']=[hex(a) for a in ANCHORS if before[a]!=after[a]]
    result['snapshotAtomic']=False;result['completed']=True

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('report','read'),nargs='?',default='report');args=parser.parse_args()
    if args.action=='report':print(json.dumps({'readOnly':True,'requestLimit':LIMIT,'hardwareRequests':0,'afBytes':860,'videoBytes':120}));return
    contract=L.FixedContract(L.FarmApplication());io=ReadOnlyIO(contract)
    result={'at':datetime.now().astimezone().isoformat(),'artifactSha256':L.ARTIFACT,'readOnly':True,'completed':False}
    try:snapshot(io,result)
    except BaseException as error:
        result['errorType']=type(error).__name__;result['error']=str(error);raise
    finally:
        result.update(requests=io.requests,writes=io.writes,allHandlesClosed=io.closed)
        path=L.HERE/'recovery'/('full-diagnostic-r4-'+datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')+'.json')
        with path.open('x',encoding='utf-8') as handle:handle.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2));print(path.name)

if __name__=='__main__':main()
