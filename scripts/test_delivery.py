import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_report_html import build
from deliver_report import atomic_json, digest, finish, mark, merge_delta, read_json, verify


def existing_state():
    return {'schema_version':'1.1', 'prompt_version':'v2.0', 'numbering_scope':'annual',
            'meetings':[{'id':'m6','date':'2026-10-10','number':6,'source_sha256':'source6'}],
            'reports':[], 'actions':[{'id':'a1','meeting_id':'m6','execution_status':'partial','updates':[]}],
            'signals':[], 'reminders':[]}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root/'档案'
        self.archive.mkdir()
        self.source = self.archive/'FM-2026-007-2026-10-17.md'
        self.source.write_text('# 测试报告\n\n## 完整正文\n内容不应丢失。\n',encoding='utf-8')
        self.receipt = self.root/'.qa/run/receipt.json'
        self.state = self.archive/'STATE-latest.json'
        atomic_json(self.state, existing_state())
        self.delta = {'base_sha256':digest(self.state.read_bytes()),'add':{
            'meetings':[{'id':self.source.stem,'date':'2026-10-17','number':7,'source_sha256':'source7'}],
            'reports':[{'id':self.source.stem,'type':'weekly_combined','meeting_id':self.source.stem,'version':1,
                        'artifacts':['档案/'+self.source.name,'档案/'+self.source.with_suffix('.html').name]}]}}
        self.patch_file = self.root/'.qa/run/delta.json'
        atomic_json(self.patch_file,self.delta)
        mark(self.receipt,'start')
        mark(self.receipt,'ready',self.source)

    def tearDown(self):
        self.temp.cleanup()

    def run_finish(self):
        return finish(self.source,self.receipt,self.state,self.patch_file)

    def test_finish_and_retry_preserve_count_and_backup(self):
        old = self.state.read_bytes()
        result = self.run_finish()
        self.assertEqual(result['archive_result'],'committed')
        self.assertEqual(len(read_json(self.state)['meetings']),2)
        backup = next((self.receipt.parent/'backups').glob('STATE-*.json'))
        self.assertEqual(backup.read_bytes(),old)
        committed = self.state.read_bytes()
        self.assertEqual(self.run_finish()['archive_result'],'already_committed')
        self.assertEqual(self.state.read_bytes(),committed)
        self.assertFalse(self.source.with_suffix('.pdf').exists())
        self.assertFalse(self.source.with_suffix('.png').exists())

    def test_backfill_keeps_newer_action_current_state(self):
        state = existing_state()
        change = {'collection':'actions','id':'a1','append':{'updates':[{'meeting_date':'2026-09-30','event':'earlier review'}]}}
        delta = {'add':{'meetings':[{'id':'m5','date':'2026-09-30','number':5,'source_sha256':'source5'}]},
                 'update':[change], 'history_confirmation':'User confirmed historical import.'}
        merged = merge_delta(state,delta)
        self.assertEqual(merged['actions'][0]['execution_status'],'partial')
        self.assertEqual(merged['meetings'][0]['id'],'m5')
        change.update(as_of='2026-09-30',set={'execution_status':'not_done'})
        with self.assertRaisesRegex(ValueError,'newer'):
            merge_delta(state,delta)
        self.assertEqual(state,existing_state())

    def test_newer_review_updates_current_fields_without_erasing_history(self):
        result = merge_delta(existing_state(),{'update':[{'collection':'actions','id':'a1','as_of':'2026-10-17','set':{'execution_status':'done'},'append':{'updates':[{'meeting_date':'2026-10-17','event':'reviewed'}]}}]})
        self.assertEqual(result['actions'][0]['execution_status'],'done')
        newer = merge_delta(existing_state(),{'update':[{'collection':'actions','id':'a1','as_of':'2026-10-17','set':{'execution_status':'done'}}]})
        with self.assertRaisesRegex(ValueError,'newer'):
            merge_delta(newer,{'update':[{'collection':'actions','id':'a1','as_of':'2026-10-15','set':{'execution_status':'partial'}}]})
        with self.assertRaisesRegex(ValueError,'append-only'):
            merge_delta(result,{'update':[{'collection':'actions','id':'a1','as_of':'2026-10-17','set':{'updates':[]}}]})

    def test_missing_confirmation_and_duplicate_source_rejected(self):
        delta={'add':{'meetings':[{'id':'m5','date':'2026-09-30','number':5,'source_sha256':'source5'}]}}
        with self.assertRaisesRegex(ValueError,'confirmation'):
            merge_delta(existing_state(),delta)
        delta['history_confirmation']='User confirmed.'
        delta['add']['meetings'][0]['source_sha256']='source6'
        with self.assertRaisesRegex(ValueError,'Duplicate source'):
            merge_delta(existing_state(),delta)

    def test_stale_state_rejected_without_overwrite(self):
        state = read_json(self.state)
        state['updated_at']='2026-10-16'
        atomic_json(self.state,state)
        before=self.state.read_bytes()
        with self.assertRaisesRegex(ValueError,'State changed'):
            self.run_finish()
        self.assertEqual(self.state.read_bytes(),before)
        self.assertEqual(read_json(self.receipt)['status'],'failed')

    def test_tampered_html_and_failed_build_do_not_commit(self):
        page=build(self.source)
        page.write_text(page.read_text(encoding='utf-8').replace('id="save-png"','id="missing-control"'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'controls'):
            verify(self.source,page)
        before=self.state.read_bytes()
        with patch('deliver_report.build',side_effect=OSError('build failed')):
            with self.assertRaises(OSError): self.run_finish()
        self.assertEqual(self.state.read_bytes(),before)

    def test_changed_body_requires_review_again(self):
        self.source.write_text('# Changed\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Body changed'):
            self.run_finish()
        self.assertEqual(len(read_json(self.state)['meetings']),1)

    def test_explicit_no_archive_and_timing(self):
        before=self.state.read_bytes()
        result=finish(self.source,self.receipt,no_archive=True)
        self.assertEqual(result['archive_result'],'not_requested')
        self.assertEqual(self.state.read_bytes(),before)
        self.assertGreaterEqual(result['analysis_wall_seconds'],0)
        self.assertGreaterEqual(result['build_verify_seconds'],0)
        with self.assertRaises(ValueError): finish(self.source,self.receipt)

    def test_lock_and_atomic_write_failure_preserve_state(self):
        lock=self.state.with_suffix('.json.delivery-lock')
        lock.write_text('another writer',encoding='utf-8')
        before=self.state.read_bytes()
        with self.assertRaises(FileExistsError): self.run_finish()
        self.assertEqual(lock.read_text(encoding='utf-8'),'another writer')
        lock.unlink()
        from deliver_report import atomic_json as real_write
        def fail_state(path,value):
            if Path(path)==self.state: raise OSError('disk full')
            return real_write(path,value)
        with patch('deliver_report.atomic_json',side_effect=fail_state):
            with self.assertRaises(OSError): self.run_finish()
        self.assertEqual(self.state.read_bytes(),before)
        self.assertFalse(lock.exists())


if __name__=='__main__':
    unittest.main()
