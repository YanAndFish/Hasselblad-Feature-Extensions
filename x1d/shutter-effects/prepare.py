"""生成独立 X1D 候选资源及入口源码，不覆盖原包，不安装或签发。"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from integrate import resources, native

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
UI=ROOT/'x1d/wifi-region/temporary-ui'
sys.path[:0] = [str(ROOT/'x1d/combined-runtime/four-module-r1'),
               str(ROOT/'x1d/candidates/ui-resident/tools')]
from compose import read_rcc
from resource_bundle import rcc

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=UI/'build/flash-ui.rcc')
    parser.add_argument('--output',type=Path,default=HERE/'build/candidate')
    args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(HERE/'build'):
        raise ValueError('Output must remain in this module build directory')
    blob=args.source.read_bytes()
    values=resources(read_rcc(blob))
    encoded=rcc(values)
    assert read_rcc(encoded)==values
    out.mkdir(parents=True,exist_ok=True)
    (out/'flash-ui.rcc').write_bytes(encoded)
    (out/'entry.cpp').write_text(native((UI/'entry.cpp').read_text(encoding='utf-8')),encoding='utf-8')
    report={'model':'X1D-50c','firmware':'1.25.0','qt':'5.5.1','durationMs':800,
            'phasesMs':[200]*4,'defaultMode':2,'modes':['关','动画','动画与声音'],
            'hardwareRequests':0,'installed':False,'installable':False,
            'sourceRccSha256':hashlib.sha256(blob).hexdigest(),
            'outputRccSha256':hashlib.sha256(encoded).hexdigest(),
            'audioRoute':'aplay -N -q -D plughw:0,0; X1D 1.25.0 card 0 verified; original aplay starts preempt custom sound; audible coexistence pending',
            'pending':['实际曝光/黑屏对应关系','播放器与原厂提示音共存','授权音频资产及安装包签发','LCD/EVF层级及冷启动验收']}
    (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
