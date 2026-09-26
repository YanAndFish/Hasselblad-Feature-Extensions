"""本地恢复文件重试不包含任何 USB 操作。"""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import mechanical_checkpoint_repair as m

class MechanicalCheckpointTests(unittest.TestCase):
    def loader(self):
        return SimpleNamespace(path=m.HERE/'build/checkpoint-model-no-file.json',record={})
    def test_transient_permission_failure_retries_only_file_save(self):
        loader=self.loader()
        with mock.patch.object(m.common.Loader,'save',side_effect=[PermissionError(),PermissionError(),None]) as save, mock.patch.object(m.time,'sleep') as sleep:
            m.save_with_retry(loader)
            self.assertEqual(save.call_count,3); self.assertEqual(sleep.call_count,2)
            self.assertEqual(loader.record['local_checkpoint_retries'],2)
    def test_persistent_failure_is_bounded(self):
        with mock.patch.object(m.common.Loader,'save',side_effect=PermissionError()) as save, mock.patch.object(m.time,'sleep'):
            with self.assertRaises(PermissionError): m.save_with_retry(self.loader())
            self.assertEqual(save.call_count,20)
    def test_other_failure_and_wrong_path_do_not_retry(self):
        with mock.patch.object(m.common.Loader,'save',side_effect=OSError()) as save:
            with self.assertRaises(OSError): m.save_with_retry(self.loader())
            self.assertEqual(save.call_count,1)
        loader=self.loader(); loader.path=m.HERE/'wrong.json'
        with self.assertRaises(RuntimeError): m.save_with_retry(loader)
