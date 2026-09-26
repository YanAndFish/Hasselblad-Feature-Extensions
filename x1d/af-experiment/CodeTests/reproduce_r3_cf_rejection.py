"""复现已捕获的CF拒绝处理：原生R3指令，位置不变和status=1为实测输入替身。"""
import sys,json
sys.dont_write_bytecode=True
from test_full_r3 import MotionCase,T

def main():
    c=MotionCase(origin=3454);rows=[]
    for cycle in range(3):
        before=len(c.targets);c.next_cycle()
        for _ in range(30):
            c.feed(3454,16000,dt=10)
            if len(c.targets)>before:break
        assert c.targets[before:]==[3518]
        for _ in range(3):c.feed(3454,16000,dt=10)
        c.reply(1);c.event();s=c.state()
        assert (s.phase,s.reason,s.physical,s.until,s.reversals)==(9,9,3454,0,0)
        rows.append({'generation':s.generation,'target':s.command_target,'position':s.physical,
            'reply':s.reply_status,'phase':s.phase,'reason':s.reason,'boundaryHint':s.until,
            'videoStarted':s.video_started})
    result={'artifactSha256':T.M['artifact_sha256'],'hardwareRequests':0,'reproducedCycles':rows,
        'scope':'执行未修改R3 ARM/Thumb及原厂启动关闭；固定位置3454和CF回复1来自实机现象输入',
        'limitations':['此测试证实拒绝后的重复失败路径，不证明镜头返回1的底层原因',
            'RTOS、镜头及图像为显式替身，不是新实机试验']}
    (T.BUILD/'observed-cf-rejection-reproduction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
