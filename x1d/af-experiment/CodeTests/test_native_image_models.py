"""用户原像素衍生曲线的固定速回放：原始ARM判向、局部辅助与独立延迟模型。

这不是闭环镜头测量。初始判向后继续回放相同固定轨迹，便于逐项对照；
减速仅记录建议，原厂越峰仅记录0x40事件，不声称已实际完成精扫或合焦。
"""
import argparse,hashlib,itertools,json,math,random,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
from test_native_af import Case,Sample,Timing,M,HERE,BUILD,config

INPUT=BUILD/'user-image-inputs.json'
D=json.loads(INPUT.read_text(encoding='utf-8'));SCALE=D['cvScale'];SIGMAS=D['sigmaPixels']

def interpolate(xs,ys,x):
    if x<=xs[0]:return ys[0]
    if x>=xs[-1]:return ys[-1]
    for i in range(1,len(xs)):
        if x<=xs[i]:
            f=(x-xs[i-1])/(xs[i]-xs[i-1]);return ys[i-1]*(1-f)+ys[i]*f
    raise AssertionError()

def values_pair(primary,secondary,sigma,pixel_noise,rng):
    if not pixel_noise:return tuple(max(1,round(interpolate(SIGMAS,row['values'],sigma)*SCALE)) for row in (primary,secondary))
    models=[[r for r in row['noiseModels'] if r['pixelNoiseStd']==pixel_noise] for row in (primary,secondary)]
    xs=[r['sigma'] for r in models[0]]
    rho=max(-1,min(1,interpolate(xs,[r['correlation'] for r in models[0]],sigma)))
    z1,z2=rng.gauss(0,1),rng.gauss(0,1);zs=(z1,rho*z1+math.sqrt(max(0,1-rho*rho))*z2)
    result=[]
    for rows,z in zip(models,zs):
        mean=interpolate(xs,[r['mean'] for r in rows],sigma);std=interpolate(xs,[r['std'] for r in rows],sigma)
        result.append(max(1,round((mean+z*std)*SCALE)))
    return tuple(result)

def direction(value):return (value>0)-(value<0)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='user-image-matrix.json');args=parser.parse_args()
    assert Path(args.output).name==args.output and args.output.endswith('.json')
    started=time.perf_counter();original=Case(False);enhanced=Case(True);calculator=Case(True)
    rows=[];generation=10
    conditions=list(itertools.product((1000,3000,8000,12000),(20,33,50),((0,0),(40,0),(0,40),(40,40)),(0,1),(-1,1)))
    for curve in D['curves']:
        secondary=next(r for r in D['curves'] if r['scene']==curve['scene'] and r['roi']==curve['roi'] and r['metric']!=curve['metric'])
        for command,interval,(command_delay,image_delay),noise,sign in conditions:
            generation+=1;rng=random.Random(generation);ss=[]
            for i in range(24):
                sample_tick=(i+1)*interval;p=round(sign*command/1000*max(0,sample_tick-command_delay));sigma=abs(p-300)/100
                cv,aux=values_pair(curve,secondary,sigma,noise,rng)
                ss.append(Sample(p,cv,sample_tick,sample_tick+image_delay,i+1,generation,15,i+1,aux))
            result={'scene':curve['scene'],'roi':curve['roi'],'metric':curve['metric'],'command':command,
                    'frameIntervalModelMs':interval,'commandDelayModelMs':command_delay,'imageDelayModelMs':image_delay,
                    'pixelNoiseStdModel':noise,'initialDirection':sign,'syntheticPeakPosition':300,
                    'positionUnitsPerBlurPixel':100,'original':None,'enhanced':None,'slowdownAdvice':None,'nativePastPeak':None}
            for case in (original,enhanced):
                case.run('na_begin',generation);case.events.clear();case.sends.clear();case.byte(0x6bb59c,0);case.byte(0x6bb59d,0)
            prior_peak=None;prior_kind=None
            for n in range(1,25):
                prefix=ss[:n];sample=prefix[-1]
                for name,case in [('original',original),('enhanced',enhanced)]:
                    if result[name] is None:
                        case.native(prefix,command=sign*command,supply=False)
                        case.u.mem_write(0x901000,bytes(sample));case.run('na_supply',0x901000);case.run(0x19d19c)
                        if case.events:
                            chosen=direction(case.sends[-1]);position_now=sign*command/1000*max(0,sample.receive_tick-command_delay)
                            position_execute=position_now+sign*command/1000*command_delay
                            result[name]={'frame':n,'tick':sample.receive_tick,'chosenDirection':chosen,'samplePosition':sample.position,
                                          'positionAtDecision':position_now,'positionAtCommandExecutionModel':position_execute,
                                          'correctAtSample':chosen==direction(300-sample.position) if sample.position!=300 else None,
                                          'correctAtExecutionModel':chosen==direction(300-position_execute) if position_execute!=300 else None}
                if sign>0 and n>=3:
                    r=calculator.core(prefix[-5:],Timing(sample.receive_tick,2,command_delay,1,.2))
                    if r.prediction_valid:
                        stable=prior_kind==r.prediction_kind and (r.prediction_kind==1 or
                               (prior_peak is not None and abs(r.peak_position-prior_peak)<=r.position_step))
                        prior_peak=r.peak_position;prior_kind=r.prediction_kind
                        if stable and r.safe_speed_ratio<1 and result['slowdownAdvice'] is None:
                            result['slowdownAdvice']={'frame':n,'samplePosition':sample.position,'tick':sample.receive_tick,
                                'actualPositionAtDecisionModel':sign*command/1000*max(0,sample.receive_tick-command_delay),
                                'predictionKind':r.prediction_kind,'predictedPeakPosition':r.peak_position if r.prediction_kind==2 else None,'ratio':r.safe_speed_ratio,
                                'beforeSyntheticPeakAtDecision':sign*command/1000*max(0,sample.receive_tick-command_delay)<300}
                    else:prior_peak=None;prior_kind=None
                    if result['nativePastPeak'] is None:
                        calculator.native(prefix,phase=4,command=command,supply=False);calculator.byte(0x6bb59c,1);calculator.byte(0x6bb59d,0)
                        calculator.events.clear();calculator.run(0x19d5c8)
                        if calculator.events:result['nativePastPeak']={'frame':n,'tick':sample.receive_tick,
                            'actualPositionAtDecisionModel':command/1000*max(0,sample.receive_tick-command_delay),
                            'event':64,'fineScanActuallyExecuted':False}
            rows.append(result)
        print(curve['scene'],curve['roi'],curve['metric'],len(conditions),'complete',flush=True)
    def summary(selected):
        item={'cases':len(selected)}
        for mode in ('original','enhanced'):
            decided=[r[mode] for r in selected if r[mode] is not None]
            item[mode]={'decided':len(decided),'undecided':len(selected)-len(decided),'byFrame3':sum(r['frame']<=3 for r in decided),
                        'wrongAtSample':sum(r['correctAtSample'] is False for r in decided),
                        'wrongAtExecutionModel':sum(r['correctAtExecutionModel'] is False for r in decided)}
        toward=[r for r in selected if r['initialDirection']>0]
        item['towardPeakCases']=len(toward);item['slowdownAdvice']=sum(r['slowdownAdvice'] is not None for r in toward)
        item['slowdownBeforePeak']=sum(r['slowdownAdvice'] is not None and r['slowdownAdvice']['beforeSyntheticPeakAtDecision'] for r in toward)
        item['nativePastPeakEvents']=sum(r['nativePastPeak'] is not None for r in toward)
        return item
    report={'kind':'原图衍生曲线+人为时序/运动/噪声的固定速离线回放','hardwareRequests':0,'actualCameraTest':False,
            'imageInputsSha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),'sourceImages':D['sources'],
            'payloadSha256':M['payload_sha256'],'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'simulatorAssumptions':{'positionPerModelMs':'command / 1000，仅模型','brakingPerModelMs2':.2,
                'processingRemainingModelMs':2,'trajectory':'指令执行后匀速，判向后不改变回放轨迹',
                'alignment':'CV、辅助指标、位置均绑定同一合成采样时刻；没有冒用收到画面时的位置',
                'auxiliaryMetric':'梯度与Laplacian互为主辅代理；不是已还原的FPGA通道A/B',
                'noiseCorrelation':'使用同一原像素噪声试验中主辅指标的相关系数，不能当作独立证据源',
                'nativePipeline':'执行原厂state3/4；样本直接置入已接受数组，尚未模拟整个原厂队列/速度过滤器'},
            'summary':summary(rows),'byNoise':{str(noise):summary([r for r in rows if r['pixelNoiseStdModel']==noise]) for noise in (0,1)},
            'seconds':time.perf_counter()-started,'trials':rows}
    (BUILD/args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('summary','byNoise','seconds')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
