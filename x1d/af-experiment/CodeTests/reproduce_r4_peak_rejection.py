"""以实机快照字段播种局部复核状态，执行冻结R4，复现噪声门槛与位置量化重复。"""
import sys,json,struct
sys.dont_write_bytecode=True
from check_r4_limits import LimitedCase,T

def main():
    T.BUILD=T.HERE/'build/full-r4';T.M=json.loads((T.BUILD/'manifest.json').read_text())
    recorded=json.loads((T.HERE/'recovery/full-diagnostic-r4-20260911-084239.json').read_text(encoding='utf-8'))
    assert recorded['artifactSha256']==T.M['artifact_sha256']
    s=recorded['state'];points=s['samplesData']
    c=LimitedCase(origin=1953);c.next_cycle()
    for name,value in {'origin':s['origin'],'probe_origin':s['probe_origin'],'refinements':1,
                       'samples':2,'noise':s['noise'],'best_cv':s['best_cv'],'best_index':1}.items():c.set(name,value)
    for i in range(2):
        c.u.mem_write(c.addr+T.State.positions.offset+2*i,struct.pack('<h',points[i]['position']))
        c.w(c.addr+T.State.cvs.offset+4*i,points[i]['cv'])
    for _ in range(30):
        c.feed(1953,points[2]['cv'])
        if c.targets:break
    assert c.targets==[2017],c.targets
    third=c.state()
    phases=[]
    # 实机同一个2017目标回报2018；允许1单位实际位置误差，回复为Reached。
    for cv in (points[3]['cv'],points[4]['cv']):
        c.position_message(2018);c.reply(0)
        for _ in range(30):
            c.feed(2018,cv)
            if len(c.targets)>len(phases)+1 or c.state().phase>=8:break
        phases.append(c.state().phase)
    final=c.state()
    assert c.targets==[2017,2017],c.targets
    assert (final.phase,final.reason,final.samples)==(9,11,5)
    result={'artifactSha256':T.M['artifact_sha256'],'source':recorded['at'],'hardwareRequests':0,
        'threshold':max(8,s['best_cv']//1000,s['noise']*6),
        'leftDrop':s['best_cv']-points[0]['cv'],'rightDrop':s['best_cv']-points[2]['cv'],
        'targets':c.targets,'returnedPosition':2018,'phase':final.phase,'reason':final.reason,
        'samples':final.samples,'repeatedSamePhysicalPoint':True,
        'limitations':['已记录的点和最终noise作为播种输入，未声称回放全部原始帧',
            '证明现有阈值和位置去重路径；不证明实际场景或光照稳定，也不证明已经物理合焦']}
    (T.BUILD/'observed-peak-rejection-reproduction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
