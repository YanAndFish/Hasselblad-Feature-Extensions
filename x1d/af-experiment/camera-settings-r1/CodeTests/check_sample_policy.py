"""以 JPEG 代理标量执行真实 ARM 局部判向；位置间距是模型输入。"""
import json,hashlib
from pathlib import Path
from test_candidate import Machine,M,config,request
HERE=Path(__file__).resolve().parents[1];OUT=HERE/'build/sample-analysis-20260912'
def main():
    path=OUT/'scores.json';data=json.loads(path.read_text(encoding='utf-8'));samples={s['file']:s for s in data['samples']};trials=[]
    for group in data['groups']:
        for omit in ([False,True] if group['label']=='电线' else [False]):
            files=[f for f in group['files'] if not (omit and samples[f]['compositionOutlier'])]
            for resampling in ('area','bilinear','point'):
                for metric in ('gradient','laplacian'):
                    cvs=[max(1,round(samples[f]['metrics'][resampling][metric]*256)) for f in files]
                    for enhanced in (False,True):
                        m=Machine()
                        if enhanced:m.process(request(2,1,config()));m.run('na_begin',2)
                        values=[m.native(cvs[:n]) for n in range(3,len(cvs)+1)]
                        trials.append({'group':group['label'],'omitCompositionOutlier':omit,'files':files,
                           'resampling':resampling,'metric':metric,'enhanced':enhanced,'proxyCv':cvs,
                           'samples':[{'count':n,'metric':v,'passesMagnitudeGateOnly':abs(v)>0.2,
                             'localDirection':'far' if v<-.2 else 'near' if v>.2 else 'undecided'} for n,v in enumerate(values,3)]})
    report={'scoresSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'payloadSha256':M['payload_sha256'],
      'farmSha256':M['baseline_sha256'],'hardwareRequests':0,'actualFocusSuccessMeasured':False,
      'positionModel':'monotonic +20 synthetic units per retained photo; user says near, fixed FARM positive means near',
      'scope':'actual original 0x19e47c and compiled na_direction; magnitude 0.2 gate applied separately',
      'notExecuted':['FIFO acceptance','original brightness floor','original n>=7 statistical filter','motor command','peak/fine/stop state machine'],
      'trials':trials}
    (OUT/'policy-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for r in trials:
        if r['resampling']=='area':print(json.dumps({k:v for k,v in r.items() if k in ('group','omitCompositionOutlier','metric','enhanced','samples')},ensure_ascii=True))
if __name__=='__main__':main()
