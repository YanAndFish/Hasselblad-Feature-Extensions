"""用户 JPEG 派生 AF 几何代理。非 LV/RAW 重建，非 FPGA CV 仿真。"""
from pathlib import Path
import os,json,hashlib,sys
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[4]
sys.path.append(str(ROOT/'x1d/af-experiment/build/user-image-tests/packages'))
OUT=ROOT/'x1d/af-experiment/camera-settings-r1/build/sample-analysis-20260912'
SRC=ROOT/'x1d/references/af-samples/20260912/219HASBL'
os.environ['MPLCONFIGDIR']=str(OUT/'mplconfig')
GROUPS=[('杆端',range(470,478)),('盒角',range(478,483)),('电线',range(483,488))]
METHODS={'area':Image.Resampling.BOX,'bilinear':Image.Resampling.BILINEAR,'point':Image.Resampling.NEAREST}
ROI=(1250,206,1498,262)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def metrics(a):
    a=np.asarray(a,dtype=np.float64);gx=np.diff(a,axis=1);gy=np.diff(a,axis=0)
    lap=a[:-2,1:-1]+a[2:,1:-1]+a[1:-1,:-2]+a[1:-1,2:]-4*a[1:-1,1:-1]
    return {'gradient':float(np.mean(gx*gx)+np.mean(gy*gy)),'laplacian':float(np.mean(lap*lap)),
            'mean':float(a.mean()),'std':float(a.std()),'p05':float(np.percentile(a,5)),'p95':float(np.percentile(a,95))}
def main():
    records=[];roi_sheet=Image.new('RGB',(6*300,3*270),'#202020');draw=ImageDraw.Draw(roi_sheet)
    for i,p in enumerate(sorted(SRC.glob('*.JPG'))):
        before=sha(p)
        with Image.open(p) as im:
            assert im.size==(4128,3096) and im.mode=='RGB'
            # 只采用 JPEG 解码像素，不调用 getexif，不复制附带元数据。
            g=Image.fromarray(np.asarray(im.convert('L'),dtype=np.uint8))
        r={'file':p.name,'sourceSha256':before,'size':[4128,3096],'metrics':{},'derived':{}}
        for method,filter in METHODS.items():
            frame=g.resize((2748,468),filter);roi=frame.crop(ROI)
            r['metrics'][method]=metrics(roi)
            if method=='area':
                for suffix,img in [('gray-2748x468',frame),('center-248x56',roi)]:
                    dest=OUT/(p.stem+'-'+suffix+'.png');img.save(dest)
                    r['derived'][suffix]={'file':dest.name,'sha256':sha(dest),'size':list(img.size)}
                # 仅作审阅的正方形显示；统计 PNG 保留非方形 AF 坐标。
                visual=roi.resize((272,218),Image.Resampling.NEAREST).convert('RGB')
                x=(i%6)*300+10;y=(i//6)*270+28;roi_sheet.paste(visual,(x,y));draw.text((x,y-20),p.stem,fill='white')
        assert before==sha(p)
        r['compositionOutlier']=p.stem=='B1489484';records.append(r)
    roi_sheet.save(OUT/'roi-contact.png')
    sources={r['file']:r for r in records};groups=[]
    for label,numbers in GROUPS:
        files=[f'B1489{n}.JPG' for n in numbers]
        groups.append({'label':label,'files':files,'grouping':'visual-content-inspection',
                       'motion':'user-confirmed manual focus adjustment toward near after each shot',
                       'actualLensPositions':None,'frameTimes':None})
    report={'method':'JPEG L8 whole-frame resampling, central ROI geometry proxy','hardwareRequests':0,
       'sensorRawReconstructed':False,'fpgaCvEmulated':False,'physicalFrameAligned':False,
       'shape':[2748,468],'roiXYWH':[1250,206,248,56],'grayscale':'Pillow RGB-to-L 8 bit, gamma-encoded JPEG values',
       'nativeSensorBitDepth':12,'proxyBitDepth':8,'primaryResampling':'BOX area averaging',
       'sensitivityResampling':['BILINEAR','NEAREST point sampling, not true sensor line skipping'],
       'groups':groups,'samples':records,'cvScaleForLocalPolicy':256,
       'limitations':['JPEG sharpening, noise reduction, tone curve and exposure affect scores',
       'sensor Bayer sampling, black borders, exact optical mapping and FPGA filters are not reconstructed',
       'group 3 second image has a changed composition; center ROI is blank wall',
       'sample spacing is unknown; no timing, speed, stopping distance or full AF success inferred']}
    (OUT/'scores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    fig,axs=plt.subplots(2,3,figsize=(13,6.4),layout='constrained')
    summary=[]
    for col,group in enumerate(groups):
        for row,metric in enumerate(('gradient','laplacian')):
            ax=axs[row,col]
            for method in METHODS:
                vals=np.array([sources[f]['metrics'][method][metric] for f in group['files']]);relative=vals/vals[0]
                ax.plot(np.arange(1,len(vals)+1),relative,'o-',label=method,markersize=3)
                summary.append({'group':group['label'],'metric':metric,'resampling':method,'relative':relative.tolist(),
                  'increasesAt':[j+2 for j,d in enumerate(np.diff(vals)) if d>0], 'maximumAt':int(vals.argmax())+1})
            if col==2:ax.axvspan(1.8,2.2,color='#c44',alpha=.15)
            ax.set_title(group['label']+' / '+metric,fontproperties=font)
            ax.set_xlabel('组内拍摄顺序（不等于等距/等时采样）',fontproperties=font)
            ax.set_ylabel('相对第一张评分',fontproperties=font);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('中央大框 JPEG 代理评分；第三组第 2 张构图变化，不能作为纯失焦样本',fontproperties=font)
    fig.savefig(OUT/'score-curves.png',dpi=150);plt.close(fig)
    (OUT/'score-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([r for r in summary if r['resampling']=='area'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
