"""核对本批离线输入、来源及真实原厂中央框计算。无设备模块。"""
from pathlib import Path
import sys,json,hashlib
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'x1d/af-experiment/CodeTests'))
from inspect_roi_native import original_roi,FARM
OUT=HERE/'build/sample-analysis-20260912'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    data=json.loads((OUT/'scores.json').read_text(encoding='utf-8'))
    sources=json.loads((OUT/'sources.json').read_text(encoding='utf-8'))
    assert len(sources)==len(data['samples'])==18
    assert original_roi((900,1200))=={'top':206,'left':1250,'width':248,'height':56}
    for a,b in zip(sources,data['samples']):
        assert a['file']==b['file'] and a['sha256']==b['sourceSha256']
        assert sha(ROOT/'x1d/references/af-samples/20260912/219HASBL'/a['file'])==a['sha256']
        for d in b['derived'].values():assert sha(OUT/d['file'])==d['sha256']
    policy=json.loads((OUT/'policy-results.json').read_text(encoding='utf-8'))
    assert policy['scoresSha256']==sha(OUT/'scores.json') and len(policy['trials'])==48
    assert all(t['localDirection']!='near' for r in policy['trials'] for t in r['samples'])
    bound=[OUT/'scores.json',OUT/'sources.json',OUT/'policy-results.json',OUT/'score-summary.json',
           OUT/'score-curves.png',OUT/'contact.png',OUT/'roi-contact.png']
    bound += [HERE/'CodeTests'/n for n in ('prepare_sample_contact.py','analyze_samples.py','check_sample_policy.py','verify_sample_artifacts.py')]
    result={'hardwareRequests':0,'originalsUnchanged':18,'derivedHashChecks':36,'policyTrials':48,
            'nativeRoiExecuted':True,'farmSha256':FARM.sha256,
            'files':{str(p.relative_to(ROOT)):sha(p) for p in bound},'passed':True}
    (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'}))
if __name__=='__main__':main()
