"""用户两幅完整取景的ROI代理指标与编译后AF闭环检查。只读图像，无USB。

Gaussian blur 是合成离焦代理，不生成或保存改造照片；不等同光学离焦、
FARM抽行或FPGA的A/B统计。仅保存指标曲线、结果表与科学曲线图。
"""
import sys,os,argparse,json,math
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];OUT=HERE/"build/user-image-tests"
OUT.mkdir(parents=True,exist_ok=True);os.environ["MPLCONFIGDIR"]=str(OUT/"mplconfig")
sys.path.append(str(OUT/"packages"))
import numpy as np
from PIL import Image
from test_full_candidate import Case,M

SIZES={"small":(.045,.06,124,28),"large":(.09,.12,248,56)}
SIGMAS=np.r_[0,np.arange(.25,24.01,.25)]
SCALE=256

def curves(path,label):
    # 只解码像素；不提取EXIF或复制输入照片。
    with Image.open(path) as image:gray=np.asarray(image.convert("L"),dtype=np.float64)
    h,w=gray.shape;results=[]
    for size,(rw,rh,aw,ah) in SIZES.items():
        x0,x1=round(w*(.5-rw/2)),round(w*(.5+rw/2))
        y0,y1=round(h*(.5-rh/2)),round(h*(.5+rh/2))
        pad=128;patch=gray[y0-pad:y1+pad,x0-pad:x1+pad]
        assert patch.shape==(y1-y0+2*pad,x1-x0+2*pad)
        spectrum=np.fft.rfft2(patch)
        radius2=np.fft.fftfreq(patch.shape[0])[:,None]**2+np.fft.rfftfreq(patch.shape[1])[None,:]**2
        energies={"gradient":[],"laplacian":[]}
        for sigma in SIGMAS:
            blurred=np.fft.irfft2(spectrum*np.exp(-2*math.pi**2*sigma**2*radius2),s=patch.shape) if sigma else patch
            roi=blurred[pad:pad+y1-y0,pad:pad+x1-x0]
            # 明示的双线性重采样代理；真实AF读出/FPGA核尚未还原。
            roi=np.asarray(Image.fromarray(roi.astype(np.float32)).resize((aw,ah),Image.Resampling.BILINEAR),dtype=np.float64)
            gx=np.diff(roi,axis=1);gy=np.diff(roi,axis=0)
            lap=roi[:-2,1:-1]+roi[2:,1:-1]+roi[1:-1,:-2]+roi[1:-1,2:]-4*roi[1:-1,1:-1]
            energies["gradient"].append(float(np.mean(gx*gx)+np.mean(gy*gy)))
            energies["laplacian"].append(float(np.mean(lap*lap)))
        for metric,values in energies.items():
            results.append({"scene":label,"roi":size,"metric":metric,"values":values,
                            "maxAtSigma":float(SIGMAS[int(np.argmax(values))]),
                            "originalProxyCv":round(values[0]*SCALE)})
    return results

def plot_report(report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    fig,axes=plt.subplots(2,2,figsize=(10,6),layout="constrained")
    for row,label in enumerate(("board_corner","wire")):
        for col,metric in enumerate(("gradient","laplacian")):
            ax=axes[row,col]
            for item in report["curves"]:
                if item["scene"]==label and item["metric"]==metric:
                    v=np.asarray(item["values"]);ax.plot(report["sigmaPixels"],v/v[0],label="小框" if item["roi"]=="small" else "大框")
            title=("板子右上角" if label=="board_corner" else "中央电线")+" / "+("梯度能量" if metric=="gradient" else "Laplacian 能量")
            ax.set_title(title,fontproperties=font)
            ax.set_xlabel("附加模糊 σ（原图像素）",fontproperties=font)
            ax.set_ylabel("相对原图的指标值",fontproperties=font)
            ax.set(xlim=(0,12),ylim=(0,1.05));ax.grid(alpha=.2);ax.legend(prop=font)
    fig.suptitle("用户图片的代理清晰度曲线：不代表真实 FPGA CV 或光学离焦",fontproperties=font)
    fig.savefig(OUT/"contrast-curves.png",dpi=160);plt.close(fig)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board",required=True,type=Path);parser.add_argument("--wire",required=True,type=Path)
    args=parser.parse_args();data=curves(args.board,"board_corner")+curves(args.wire,"wire")
    print("ROI_PROXY_CURVES_READY",flush=True)
    trials=[]
    for item in data:
        for units in (50,100,200):
            for peak in (-300,300):
                for far in (False,True):
                    def curve(p):
                        sigma=abs(p-peak)/units
                        return max(1,round(float(np.interp(sigma,SIGMAS,item["values"]))*SCALE))
                    case=Case(far=far);case.start();state=case.simulate(curve)
                    focused=state.phase==8
                    trial={"scene":item["scene"],"roi":item["roi"],"metric":item["metric"],
                        "positionUnitsPerBlurPixel":units,"syntheticPeakPosition":peak,"initialNegative":far,
                        "phase":state.phase,"reason":state.reason,"reportedSuccess":focused,
                        "finalTarget":state.target,"targetError":abs(state.target-peak) if focused else None,
                        "ticks":(case.time-state.started)&0xffffffff,"reversals":state.reversals,
                        "commands":case.sends,"targets":case.targets,"confirmations":state.confirmations}
                    assert state.phase in (8,9) and case.sends[-1]==0 and not case.native_search
                    assert trial["ticks"]<=2420
                    trial["nearSyntheticPeak"]=focused and abs(state.target-peak)<=max(15,units*.25)
                    trials.append(trial)
        print(item["scene"],item["roi"],item["metric"],"originalProxyCv",item["originalProxyCv"],flush=True)
    summaries=[]
    for item in data:
        matching=[t for t in trials if all(t[k]==item[k] for k in ("scene","roi","metric"))]
        summaries.append({**{k:item[k] for k in ("scene","roi","metric","originalProxyCv","maxAtSigma")},
            "trials":len(matching),"success":sum(t["reportedSuccess"] for t in matching),
            "nearSyntheticPeak":sum(t["nearSyntheticPeak"] for t in matching),
            "failureReasons":sorted({t["reason"] for t in matching if not t["reportedSuccess"]})})
    report={"method":"synthetic_gaussian_blur_of_user_supplied_pixels_with_two_proxy_metrics",
        "payloadSha256":M["payload_sha256"],"hardwareRequests":0,"fpgaCvEmulated":False,
        "physicalDefocusEmulated":False,"originalImagesSaved":False,"cvScale":SCALE,
        "centralRoiPreserved":True,"sigmaPixels":SIGMAS.tolist(),"curves":data,"summary":summaries,"trials":trials}
    (OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    plot_report(report)
    print(json.dumps({"trials":len(trials),"success":sum(t["reportedSuccess"] for t in trials),
        "nearSyntheticPeak":sum(t["nearSyntheticPeak"] for t in trials),"summary":summaries},indent=2),flush=True)

if __name__=="__main__":main()
