"""真实文件持久化与离线装载核心的失败顺序；无硬件模块。"""
import sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r3_install_journal import InstallJournal
from r3_install_plan import InstallPlan,MemoryBackend,OfflineInstaller,M,BUILD
from test_r3_install_barrier import FarmApplication

class InstallJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=InstallPlan(FarmApplication())
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='journal-test-',dir=BUILD)
        assert Path(self.temp.name).resolve().is_relative_to(BUILD.resolve())
        self.path=Path(self.temp.name)/'record.json'
        self.journal=InstallJournal(self.path,M['artifact_sha256'])
    def tearDown(self):self.journal.close();self.temp.cleanup()
    def test_before_effect_and_unknown_after_effect_both_keep_intent_and_never_resume(self):
        # 两种异常对磁盘记录相同，恢复工具不能把请求失败等同于没有生效。
        for after in (False,True):
            if after:
                self.journal.close();self.path=Path(self.temp.name)/'after.json'
                self.journal=InstallJournal(self.path,M['artifact_sha256'])
            b=MemoryBackend(self.plan,fail_at=0,after_effect=after)
            i=OfflineInstaller(self.plan,b,self.journal)
            with self.assertRaises(IOError):i.stage()
            r=InstallJournal.inspect(self.path,M['artifact_sha256'])
            self.assertEqual(r['sequence'],1);self.assertIsNotNone(r['inFlight'])
            self.assertEqual(len(b.operations),int(after))
            with self.assertRaises(RuntimeError):self.journal.begin('retry',i.inflight)
            with self.assertRaises(RuntimeError):InstallJournal(self.path,M['artifact_sha256'])
    def test_failed_intent_persistence_prevents_mutation_and_failed_completion_keeps_pending(self):
        b=MemoryBackend(self.plan);i=OfflineInstaller(self.plan,b,self.journal)
        with patch.object(self.journal,'persist',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):i.stage()
        self.assertEqual(b.operations,[])
        self.journal.close();self.path=Path(self.temp.name)/'completion.json'
        self.journal=InstallJournal(self.path,M['artifact_sha256'])
        b=MemoryBackend(self.plan);i=OfflineInstaller(self.plan,b,self.journal)
        persist=self.journal.persist;calls=[]
        def fail_completion(record):
            calls.append(record)
            if len(calls)==2:raise OSError('completion snapshot unavailable')
            return persist(record)
        with patch.object(self.journal,'persist',side_effect=fail_completion):
            with self.assertRaises(OSError):i.stage()
        self.assertEqual(len(b.operations),1)
        self.assertIsNotNone(InstallJournal.inspect(self.path,M['artifact_sha256'])['inFlight'])
        with self.assertRaises(RuntimeError):self.journal.complete()
    def test_open_anchor_and_unavailable_replace_do_not_interrupt_append_only_journal(self):
        b=MemoryBackend(self.plan);i=OfflineInstaller(self.plan,b,self.journal)
        address,value=next(iter(self.plan.helper.items()));i.write(address,value)
        r=InstallJournal.inspect(self.path,M['artifact_sha256'])
        self.assertEqual(r['sequence'],1);self.assertIsNone(r['inFlight'])
        original=self.path.read_bytes()
        with self.path.open('r',encoding='utf-8') as held:
            with patch('r3_install_journal.os.replace',side_effect=PermissionError('reader denies replacement')) as replace:
                i.write(address,value);replace.assert_not_called()
            self.assertTrue(held.read())
        self.assertEqual(len(b.operations),2);self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(InstallJournal.inspect(self.path,M['artifact_sha256'])['sequence'],2)
    def test_partial_tail_retains_last_durable_intent_and_broken_chain_is_rejected(self):
        self.journal.begin('pending',('write',next(iter(self.plan.helper)),0))
        self.journal.close()
        with self.journal.events_path.open('a',encoding='utf-8') as handle:handle.write('{"index":')
        r=InstallJournal.inspect(self.path,M['artifact_sha256'])
        self.assertIsNotNone(r['inFlight']);self.assertTrue(r['journalAudit']['incompleteTail'])
        data=self.journal.events_path.read_text(encoding='utf-8')
        self.journal.events_path.write_text(data.replace('pending','damaged',1),encoding='utf-8')
        with self.assertRaises(ValueError):InstallJournal.inspect(self.path,M['artifact_sha256'])

    @classmethod
    def tearDownClass(cls):
        (BUILD/'installation-journal.json').write_text(json.dumps({
            'artifactSha256':M['artifact_sha256'],'hardwareRequests':0,'installReady':False,
            'scope':'真实电脑文件记录与离线内存事务；不是USB/SGI故障恢复',
            'beforeEffectAndAfterEffectRemainUncertain':True,'automaticResume':False,
            'limitations':['不模拟Windows断电后的文件系统持久性',
                '恢复记录仅供离线审阅，无自动硬件恢复入口']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
