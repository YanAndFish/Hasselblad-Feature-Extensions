"""对实际离线安装事务注入每一个写入／缓存步骤前后的失败；无设备适配器。"""
import sys,json,unittest
sys.dont_write_bytecode=True
from r4_install_plan import InstallPlan,MemoryBackend,OfflineInstaller,visible_safety,M,BUILD,HOOK,COUNT,WAKE_HOOK,SENT
from test_r4_install_barrier import FarmApplication
from test_r4_task_wake import TaskWakeCase

class InstallPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.farm=FarmApplication();cls.plan=InstallPlan(cls.farm)
        c=TaskWakeCase(cls.farm);c.block_af();cls.native_counter=c.request(schedule_at_svc=True)
    def staged(self):
        b=MemoryBackend(self.plan);i=OfflineInstaller(self.plan,b);i.stage();return i,b
    def test_no_fresh_ack_non_idle_or_changed_baseline_stops_before_body_upload(self):
        for change in ('missing_ack','non_idle','changed_gate','changed_body','changed_wake','missing_sent'):
            i,b=self.staged()
            if change!='missing_ack':b.observe_native_idle_ack(self.native_counter)
            if change=='non_idle':b.memory[0x6bb46c]=3
            if change=='changed_gate':b.memory[HOOK]=0
            if change=='changed_body':b.memory[0x19bfb8]^=1
            if change=='changed_wake':b.memory[WAKE_HOOK]=0
            if change=='missing_sent':b.memory[SENT]=0
            count=len(b.operations)
            with self.assertRaises(RuntimeError):i.install()
            self.assertEqual(len(b.operations),count)
    def test_every_failed_prefix_retains_complete_executable_entry(self):
        baseline=MemoryBackend(self.plan);i=OfflineInstaller(self.plan,baseline)
        i.stage();stage_count=len(baseline.operations)
        baseline.observe_native_idle_ack(self.native_counter);i.install()
        total=len(baseline.operations);self.assertTrue(visible_safety(self.plan,baseline))
        for after in (False,True):
            for fail in range(total):
                b=MemoryBackend(self.plan,fail_at=fail,after_effect=after);i=OfflineInstaller(self.plan,b)
                with self.assertRaises(IOError):
                    i.stage();b.observe_native_idle_ack(self.native_counter);i.install()
                self.assertIsNotNone(i.inflight,(after,fail))
                self.assertTrue(visible_safety(self.plan,b),(after,fail))
                self.assertEqual(b.hardware_requests,0)
        (BUILD/'installation-failure-model.json').write_text(json.dumps({
            'artifactSha256':M['artifact_sha256'],'operationCount':total,'stageOperationCount':stage_count,
            'failureCases':total*2,'passed':True,'hardwareRequests':0,'hardwareLoaderImplemented':False,
            'installReady':False,'limitations':['离线内存事务，尚未接入USB与SGI缓存同步',
                '指令可见性按显式缓存同步模型，不是CPU缓存一致性实测',
                '输入ACK来自原生诊断任务/事件发布/等待返回/屏障，上下文切换为电脑调度替身',
                '失败时仅停止并保留入口，没有自动恢复或清除辅助代码']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def test_reversed_publication_order_is_detected_by_dependency_check(self):
        b=MemoryBackend(self.plan)
        # 反例：未暂停AF就先覆盖正文；以及提前开放最终入口。
        address=next(a for a in self.plan.code if a<M['base'])
        b.memory[address]=self.plan.code[address]
        self.assertFalse(visible_safety(self.plan,b))
        b=MemoryBackend(self.plan);b.visible[HOOK]=self.plan.final_gate
        self.assertFalse(visible_safety(self.plan,b))
        b=MemoryBackend(self.plan);b.visible[WAKE_HOOK]=self.plan.wake_hook
        self.assertFalse(visible_safety(self.plan,b))

if __name__=='__main__':unittest.main(verbosity=2)
