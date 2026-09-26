"""45秒固定只读计时采样；由用户手动对焦，不启动或更改相机操作。"""
import sys,json,time,argparse
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
import read_full_diagnostic_r3 as D
L=D.L
FIELDS={'request':D.VIDEO+16,'target':D.VIDEO+24,'ack':D.VIDEO+20,
        'ready_tick':D.VIDEO+104,'session':D.VIDEO+12,'generation':D.AF+16,
        'video_started':D.AF+824,'video_state':D.AF+820,'phase':D.AF+20,
        'switches':D.VIDEO+112,'result':D.VIDEO+28,'now':0x6badd0,
        'reason':D.AF+24,'physical':D.AF+168,'command_target':D.AF+140,
        'reply_status':D.AF+152,'command':D.AF+80}
LIMIT=10000;DURATION=45;INTERVAL=.1

class TimingIO(L.FixedIO):
    def __init__(self,contract):
        super().__init__(contract)
        self.allowed_reads=set(FIELDS.values())|{L.CB,L.ARG,L.WAKE_HOOK,D.AF,D.AF+4,D.AF+856,D.VIDEO,D.VIDEO+4,D.VIDEO+116}
        if not self.allowed_reads<=contract.reads:raise ValueError('outside reviewed read set')
    def exchange(self,kind,a=None,v=None):
        if self.requests>=LIMIT or kind not in ('read','version') or v is not None:
            raise ValueError('fixed read-only timing operation required')
        if kind=='read' and a not in self.allowed_reads:raise ValueError('fixed timing read address')
        return super().exchange(kind,a,v)

def sample(io,origin):
    r={'hostStartSeconds':time.perf_counter()-origin}
    r.update({name:io.read(address) for name,address in FIELDS.items()})
    r['requestAfter']=io.read(FIELDS['request']);r['generationAfter']=io.read(FIELDS['generation'])
    r['startedAfter']=io.read(FIELDS['video_started'])
    r['hostEndSeconds']=time.perf_counter()-origin
    r['stableBinding']=r['request']==r['requestAfter'] and r['generation']==r['generationAfter'] and r['video_started']==r['startedAfter']
    return r

def summarize(rows):
    observed={};gaps=[];previous=None
    for row in rows:
        if not row['stableBinding']:continue
        req=row['request']
        if previous is not None and req>previous+1:gaps.append({'afterRequest':previous,'nextObservedRequest':req})
        previous=req
        if not req or row['session']!=row['generation'] or not row['video_started']:continue
        key=(req,row['target'],row['generation'],row['video_started'])
        item=observed.setdefault(key,{'request':req,'targetMode':row['target'],'generation':row['generation'],
            'requestStartedTick':row['video_started'],'firstObservedSeconds':row['hostEndSeconds'],
            'requestObservedBeforeAck':False,'successfulReadyTicks':None,'newStatisticsObservedByTick':None})
        if row['ack']!=req:item['requestObservedBeforeAck']=True
        delta=(row['ready_tick']-row['video_started'])&0xffffffff
        if row['ack']==req and row['result']==0 and delta<60000:
            item['readyTick']=row['ready_tick'];item['successfulReadyTicks']=delta
            if row['video_state']==0 and row['phase']<8:
                item['newStatisticsObservedByTick']=item['newStatisticsObservedByTick'] or row['now']
    rate=None
    if len(rows)>1:
        a,b=rows[0],rows[-1];elapsed=b['hostEndSeconds']-a['hostEndSeconds']
        if elapsed>=1:rate=((b['now']-a['now'])&0xffffffff)/elapsed
    return {'transitions':list(observed.values()),'missedRequestRanges':gaps,'observedTicksPerHostSecond':rate,
        'screenRefreshMeasured':False,'method':'AF request-start tick to video configuration-ready tick; screen display is outside these fields',
        'limitations':['USB sampling may affect scheduling; these are observed instrumented timings',
            'Polling can miss complete intervening transitions; no invented timestamps',
            'ready_tick precedes statistics restart and does not prove displayed-frame completion']}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('report','read'),nargs='?',default='report');args=parser.parse_args()
    if args.action=='report':print(json.dumps({'hardwareRequests':0,'readOnly':True,'durationSeconds':DURATION,'requestLimit':LIMIT}));return
    contract=L.FixedContract(L.FarmApplication());io=TimingIO(contract);rows=[]
    result={'at':datetime.now().astimezone().isoformat(),'artifactSha256':L.ARTIFACT,'readOnly':True,'completed':False}
    try:
        io.exchange('version')
        guards={L.CB:L.ORIG_CB,L.ARG:L.ORIG_ARG,L.WAKE_HOOK:contract.plan.wake_original,
            D.AF:L.M['stateMagic'],D.AF+4:6,D.AF+856:L.M['canary'],D.VIDEO:0x46313630,D.VIDEO+4:1,D.VIDEO+116:0x30363146}
        for a,v in guards.items():
            if io.read(a)!=v:raise RuntimeError('installed timing guard mismatch '+hex(a))
        print(json.dumps({'stage':'ready_for_user_manual_af','durationSeconds':DURATION,'writes':0}),flush=True)
        origin=time.perf_counter();due=origin
        while time.perf_counter()-origin<DURATION and io.requests+len(FIELDS)+3<LIMIT:
            rows.append(sample(io,origin));due+=INTERVAL
            delay=due-time.perf_counter()
            if delay>0:time.sleep(min(delay,INTERVAL))
        result.update(summarize(rows));result['completed']=True
    except BaseException as error:result['errorType']=type(error).__name__;raise
    finally:
        result.update(rows=rows,requests=io.requests,writes=io.writes,allHandlesClosed=io.closed)
        path=L.HERE/'recovery'/('r3-transition-timing-'+datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')+'.json')
        with path.open('x',encoding='utf-8') as handle:handle.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2));print(path.name)

if __name__=='__main__':main()
