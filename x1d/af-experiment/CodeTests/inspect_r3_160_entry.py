"""现装R3的160入口条件：原生候选执行；运动、视频服务和时钟仍为模型。"""
import sys,json,math
sys.dont_write_bytecode=True
from test_r3_video_flow import JointCase,T

def state(c):
    s=c.state();v=c.video()
    return {'generation':s.generation,'phase':s.phase,'cvProfile':s.cv_profile,
        'videoSession':v.session,'videoRequest':v.request,'videoAck':v.ack,
        'videoStarted':s.video_started,'reason':s.reason}

def main():
    cases=[]
    c=JointCase(origin=3454);c.next_cycle();before=state(c)
    assert c.video().session==c.state().generation and c.state().cv_profile==0
    assert c.video().request==0
    for _ in range(30):
        c.feed(3454,16000,dt=10)
        if c.targets:break
    assert c.targets==[3518]
    for _ in range(3):c.feed(3454,16000,dt=10)
    c.reply(1);c.event()
    assert c.state().phase==9 and c.video().request==0
    cases.append({'case':'eligible_but_initial_cf_rejected','before':before,'after':state(c),
        'meaning':'满足160资格仍不会在起步微动前请求切换；CF拒绝可在请求之前结束AF'})
    c=JointCase();c.next_cycle();before=state(c)
    s=c.simulate_joint(lambda p:10000*math.exp(-.5*((p-300)/400)**2))
    assert s.phase==8 and c.transitions and c.transitions[0]['target']==7
    cases.append({'case':'normal_modeled_motion_reaches_later_160_request','before':before,'after':state(c),
        'firstTransition':c.transitions[0],'transitionCount':len(c.transitions),
        'meaning':'正常模型运动能到达后续160请求；这里的时间和视频响应不是实测'})
    for label,configure in (
        ('digital_gain_above_one',lambda c:c.w(0x6c173c,0x40000000)),
        ('native_video_not_mode5',lambda c:c.u.mem_write(0x6c1778,b'\x02')),
        ('native_video_inactive',lambda c:c.u.mem_write(0x6c176c,b'\x00')),
        ('focus_box_outside_short_window',lambda c:c.w(0x6cc59c,100|(1250<<16)))):
        c=JointCase();configure(c);c.next_cycle()
        assert c.video().session==0 and c.video().request==0 and c.state().phase==2
        cases.append({'case':label,'state':state(c),
            'meaning':'起步资格不满足时保留全幅；现有状态没有保存具体拒绝原因'})
    result={'artifactSha256':T.M['artifact_sha256'],'hardwareRequests':0,'cases':cases,
        'limitations':['固定现装二进制；没有修改候选或相机','资格失败场景是指定输入，不代表本次相机具体失败条件',
            '模型完成切换时间不能作为实机耗时']}
    (T.BUILD/'160-entry-gates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
