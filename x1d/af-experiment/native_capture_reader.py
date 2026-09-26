"""校验本轮装载身份并读取标量 AF 记录；默认 report 离线，不读取图像。"""
import argparse,hashlib,json,struct,sys
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
from native_install import *
from native_loader import NativeIO
from r3_install_journal import InstallJournal

def signed(v):return v-0x100000000 if v&0x80000000 else v
def primary(raw):
    a,b,mode,_=raw['data']
    if mode==0:return (a+b)&0xffffffff
    if mode in (1,2):
        v=a+(b>>(2 if mode==1 else 1))
        return v if v<=0xffffffff else None
    if mode==3:return a
    if mode==4:return b
    return None

def decode(header,raw_rows,af_rows,control_rows=()):
    if len(header)!=12 or header[:2]!=[0x3150434e,2] or header[6]!=1 or header[7]!=EXEC_MAGIC or any(header[9:12]):
        raise ValueError('capture header identity')
    if any(not 0<=header[i]<0x80000000 for i in (3,4,8)):raise ValueError('capture counter bounds')
    def rows(values,sequence,capacity,stream):
        first=max(1,sequence-capacity+1)
        if len(values)!=sequence-first+1:raise ValueError('snapshot record count')
        result=[]
        for n,v in enumerate(values,first):
            kinds=(1,) if stream=='irq' else ((5,6) if stream=='control' else (2,3,4,6))
            if len(v)!=9 or v[0]!=n*2 or v[1] not in kinds:
                raise ValueError('torn/overwritten record or kind')
            if v[4]>8 or (not v[4] and v[1]!=5):raise ValueError('AF state outside record contract')
            if v[1]==6 and (v[5] not in ((1,2) if stream=='control' else (0,))):raise ValueError('command writer mismatch')
            result.append({'sequence':n,'stream':stream,'kind':v[1],'observedTick':v[2],'generation':v[3],'state':v[4],'data':list(v[5:])})
        return result
    raw=rows(raw_rows,header[3],64,'irq');af=rows(af_rows,header[4],128,'data')
    control=rows(control_rows,header[8],32,'control')
    fifo_cv={};fifo_position={};pairs=[];last_raw={};generation=None
    for row in af:
        if row['generation']!=generation:
            fifo_cv={};fifo_position={};generation=row['generation']
        data=row['data']
        if row['kind']==2:
            if data[1]>=5:raise ValueError('invalid CV slot')
            fifo_cv[data[1]]=row
        elif row['kind']==3:
            if data[1]>=5 or data[2]>=100 or not -32768<=signed(data[0])<=32767:raise ValueError('invalid position record')
            fifo_position[data[1]]=row
        elif row['kind']==4:
            count,position,cv,heads=data
            if not 1<=count<=500 or not -32768<=signed(position)<=32767:raise ValueError('accepted array bounds')
            cv_head,po_head=heads&65535,heads>>16
            if cv_head>=5 or po_head>=5:raise ValueError('native FIFO head bounds')
            c=fifo_cv.get((cv_head+4)%5);p=fifo_position.get((po_head+4)%5)
            matched=bool(c and p and c['data'][0]==cv and p['data'][0]==position)
            candidates=[]
            if matched:
                previous=last_raw.get(generation,0)
                candidates=[r for r in raw if r['generation']==generation and r['sequence']>previous and primary(r)==cv and
                    (c['observedTick']-r['observedTick'])&0xffffffff<=0x7fffffff]
            unique=candidates[0] if len(candidates)==1 else None
            if unique:last_raw[generation]=unique['sequence']
            pair={'generation':generation,'nativeCount':count,'position':signed(position),'cv':cv,
                'acceptedObservedTick':row['observedTick'],'nativeFifoValuesMatched':matched,
                'cvObservedTick':c['observedTick'] if matched else None,
                'positionObservedTick':p['observedTick'] if matched else None,
                'lensSequence':p['data'][2] if matched else None,
                'rawCandidateCount':len(candidates),'rawSequence':unique['sequence'] if unique else None,
                'rawObservedTick':unique['observedTick'] if unique else None,
                'physicalFrameAlignmentVerified':False,'sampleTick':None,'algorithmMetadataFlags':0}
            pairs.append(pair)
    return {'kind':'native-af-scalar-observation','captureAbi':2,'generation':header[2],
        'rawSequence':header[3],'afSequence':header[4],'controlSequence':header[8],
        'invalidRecords':header[5],'rawTruncated':header[3]>64,'afTruncated':header[4]>128,'controlTruncated':header[8]>32,
        'rawRecords':raw,'afRecords':af,'controlRecords':control,'nativePairs':pairs,'predictionCalibrationAvailable':False,
        'limits':['所有 tick 均为机身观察时刻；没有把它转换成曝光/镜头采样时刻',
            'IRQ、AF_SERVICE 与 AF_SERVICE_SM 分别保存；跨任务相同 tick 不代表可确定的执行先后',
            'FIFO 数值匹配和唯一 CV 候选只供核对；不能证明物理同帧',
            '重复 CV、缺失记录或环覆盖会失去对应关系；保留不确定项而不选最近一项冒充匹配']}

class CaptureReadIO(NativeIO):
    def exchange(self,kind,a=None,v=None):
        if kind not in ('read','version'):raise ValueError('capture reader is read-only')
        return super().exchange(kind,a,v)

class Snapshot:
    def __init__(self,c,io,record,manifest,blob):
        self.c,self.io,self.record,self.manifest=c,io,record,manifest
        if (not record.get('installed') or record.get('phase')!='installed_observation_until_restart' or
            record.get('inFlight') is not None or record.get('cacheInFlight') is not None or not record.get('allHandlesClosed')):
            raise ValueError('completed installation record required')
        if record.get('bootstrapNonce')!=c.nonce or record.get('contractSha256')!=c.identity:
            raise ValueError('installation identity')
        response=record['allocationResponse'];header=(0,response[10]|0x80000000)
        c.bind(response,header,manifest,blob)
    def read_words(self,a,n):return [self.io.read(a+4*i) for i in range(n)]
    def read(self):
        c=self.c;m=self.manifest;io=self.io;io.exchange('version')
        for a,v in ((GATE_HOOK,c.bootstrap_hooks[GATE_HOOK][0]),(WAKE_HOOK,c.bootstrap_hooks[WAKE_HOOK][0]),(CB,ORIG_CB),(ARG,ORIG_ARG)):
            if io.read(a)!=v:raise RuntimeError('installation/cache entry changed')
        if (io.read(PENDING)|io.read(ACTIVE))&0x8000:raise RuntimeError('shared SGI busy')
        if io.read(0x6bb46c)&255:raise RuntimeError('AF must be idle for bounded snapshot')
        if self.read_words(c.request,13)!=self.record['allocationResponse']:raise RuntimeError('installation nonce/allocation changed')
        raw_pointer=c.allocation[8]
        if self.read_words(raw_pointer-8,2)!=[0,c.allocation[10]|0x80000000]:raise RuntimeError('owned allocation changed')
        for a,v in c.candidate_words.items():
            if a<m['state_start'] and io.read(a)!=v:raise RuntimeError('resident AF code changed')
        for a,old,new in m['emulatorOnlyHooks']:
            if io.read(a)!=new:raise RuntimeError('resident hook changed')
        start=m['symbols']['nc_capture'];before=self.read_words(start,12)
        if any(before[i]>=0x80000000 for i in (3,4,8)):raise RuntimeError('capture counter exhausted')
        def ring(sequence,capacity,base):
            return [self.read_words(base+((n-1)&(capacity-1))*36,9) for n in range(max(1,sequence-capacity+1),sequence+1)]
        raw=ring(before[3],64,start+48);af=ring(before[4],128,start+48+64*36)
        control=ring(before[8],32,start+48+(64+128)*36)
        after=self.read_words(start,12)
        if before!=after or io.read(0x6bb46c)&255:raise RuntimeError('capture changed during read; no retry')
        result=decode(before,raw,af,control)
        result.update(bootstrapNonce=c.nonce,payloadSha256=m['payload_sha256'],baselineSha256=BASELINE_SHA,
            hardwareRequests=io.requests if io.is_hardware else 0,allHandlesClosed=io.closed)
        return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('report','read'),nargs='?',default='report')
    p.add_argument('--journal',type=Path);args=p.parse_args()
    if args.journal is None:
        print(json.dumps({'hardwareRequests':0,'requires':'本轮已完成装载的恢复记录；默认不连接相机'}));return
    path=args.journal.resolve()
    if not path.is_relative_to(HERE/'recovery'):raise ValueError('current AF recovery path required')
    c=NativeContract();record=InstallJournal.read_record(path,c.identity)
    if record['journalAudit']['incompleteTail']:raise ValueError('incomplete installation journal')
    c=NativeContract(c.farm,nonce=record['bootstrapNonce']);manifest=record['candidate']
    folder=HERE/'build/native-capture-r1'/f"{manifest['base']:08x}"
    disk=json.loads((folder/'capture-manifest.json').read_text(encoding='utf-8'))
    if disk!=manifest:raise ValueError('resident candidate manifest identity')
    blob=(folder/'candidate.bin').read_bytes();io=CaptureReadIO(c);snapshot=Snapshot(c,io,record,manifest,blob)
    if args.action=='report':
        print(json.dumps({'hardwareRequests':0,'bootstrapNonce':c.nonce,'payloadSha256':manifest['payload_sha256'],'maximumRecords':224}));return
    result=snapshot.read();stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    output=HERE/'recovery'/('native-capture-'+stamp+'.json')
    with output.open('x',encoding='utf-8') as file:json.dump(result,file,ensure_ascii=False,indent=2);file.write('\n')
    print(json.dumps({'output':output.name,'hardwareRequests':io.requests,'allHandlesClosed':io.closed,
        'rawRecords':len(result['rawRecords']),'afRecords':len(result['afRecords']),
        'controlRecords':len(result['controlRecords']),'nativePairs':len(result['nativePairs'])}));return

if __name__=='__main__':main()
