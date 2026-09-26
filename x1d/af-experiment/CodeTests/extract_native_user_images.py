"""重新读取用户两张静态 PNG 的像素，生成本轮图像侧代理输入；不读取 EXIF 或设备。"""
import argparse,hashlib,json,math,sys
from pathlib import Path
sys.dont_write_bytecode=True
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
OUT=HERE/'build/native-af-r1';SCALE=256
SIGMAS=np.arange(0,24.01,.25)
SIZES={'small':(.045,.06,124,28),'large':(.09,.12,248,56)}

def metrics(roi):
    gx=np.diff(roi,axis=1);gy=np.diff(roi,axis=0)
    lap=roi[:-2,1:-1]+roi[2:,1:-1]+roi[1:-1,:-2]+roi[1:-1,2:]-4*roi[1:-1,1:-1]
    return {'gradient':float(np.mean(gx*gx)+np.mean(gy*gy)),
            'laplacian':float(np.mean(lap*lap))}

def extract(path,label):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with Image.open(path) as image:
        image.load();size=list(image.size);gray=np.asarray(image.convert('L'),dtype=np.float64)
    h,w=gray.shape;rows=[];random=np.random.default_rng(751250)
    for name,(rw,rh,aw,ah) in SIZES.items():
        x0,x1=round(w*(.5-rw/2)),round(w*(.5+rw/2));y0,y1=round(h*(.5-rh/2)),round(h*(.5+rh/2))
        pad=128;patch=gray[y0-pad:y1+pad,x0-pad:x1+pad]
        assert patch.shape==(y1-y0+pad*2,x1-x0+pad*2)
        spectrum=np.fft.rfft2(patch)
        radius2=np.fft.fftfreq(patch.shape[0])[:,None]**2+np.fft.rfftfreq(patch.shape[1])[None,:]**2
        values={k:[] for k in ('gradient','laplacian')};noise_rows=[]
        for sigma in SIGMAS:
            blurred=np.fft.irfft2(spectrum*np.exp(-2*math.pi**2*sigma*sigma*radius2),s=patch.shape) if sigma else patch
            roi=blurred[pad:pad+y1-y0,pad:pad+x1-x0]
            roi=np.asarray(Image.fromarray(roi.astype(np.float32)).resize((aw,ah),Image.Resampling.BILINEAR),dtype=np.float64)
            for key,value in metrics(roi).items():values[key].append(value)
            if sigma in (0,2,6,12,24):
                for std in (1,2,4):
                    # 在代理统计图上叠加确定种子的高斯像素噪声，仅用于模型，不是传感器噪声标定。
                    measured=[metrics(roi+random.normal(0,std,roi.shape)) for _ in range(32)]
                    noise_rows.append({'sigma':float(sigma),'pixelNoiseStd':std,
                        'correlation':float(np.corrcoef([r['gradient'] for r in measured],[r['laplacian'] for r in measured])[0,1]),
                        'metrics':{key:{'mean':float(np.mean([r[key] for r in measured])),
                                        'std':float(np.std([r[key] for r in measured],ddof=1))} for key in values}})
        for metric,curve in values.items():
            rows.append({'scene':label,'roi':name,'metric':metric,'inputSha256':digest,
                         'roiPixels':[x0,y0,x1-x0,y1-y0],'proxyDimensions':[aw,ah],
                         'values':curve,'originalProxyCv':round(curve[0]*SCALE),
                         'noiseModels':[{'sigma':r['sigma'],'pixelNoiseStd':r['pixelNoiseStd'],'correlation':r['correlation'],**r['metrics'][metric]} for r in noise_rows]})
    return {'scene':label,'sourceBasename':path.name,'sha256':digest,'dimensions':size,
            'kind':'用户提供的单张完整取景静态PNG','exifRead':False,'pixelsCopied':False,
            'measuredFrameSequence':False,'lensPositionAvailable':False,'sampleTimeAvailable':False},rows

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--board',required=True,type=Path);parser.add_argument('--wire',required=True,type=Path)
    parser.add_argument('--reference',required=True,type=Path,help='使用者本地先前像素曲线；不使用公开合成样本')
    args=parser.parse_args();sources=[];curves=[]
    for label,path in [('board_corner',args.board),('wire',args.wire)]:
        source,rows=extract(path,label);sources.append(source);curves+=rows
        print(label,source['sha256'],source['dimensions'],flush=True)
    old=json.loads(args.reference.read_text(encoding='utf-8'))
    differences=[]
    for row in curves:
        prior=next(r for r in old['curves'] if all(r[k]==row[k] for k in ('scene','roi','metric')))
        differences.append(max(abs(a-b) for a,b in zip(prior['values'],row['values'])))
    report={'method':'user_pixels_with_synthetic_gaussian_blur_and_proxy_metrics','sources':sources,
            'sigmaPixels':SIGMAS.tolist(),'cvScale':SCALE,'curves':curves,'hardwareRequests':0,
            'fpgaCvEmulated':False,'physicalDefocusEmulated':False,'actualDelayMeasured':False,
            'noiseModel':'代理统计图上的合成像素噪声；固定种子751250，每条件32次，保留主辅指标相关系数；非真实传感器噪声',
            'maxAbsoluteDifferenceFromEarlierPixelCurves':max(differences),
            'extractorSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'user-image-inputs.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'curves':len(curves),'maxDifferenceFromEarlierPixelCurves':max(differences),'hardwareRequests':0}))

if __name__=='__main__':main()
