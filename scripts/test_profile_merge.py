"""Regression cases for schema keys colliding with nested decision/custom keys."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from profile_store import merge, update_profile, read_profile, status


class ProfileMergeTests(unittest.TestCase):
    def test_later_family_decision_persists_and_keeps_existing_data(self):
        for decision in ('deferred', 'declined'):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory)
                first = update_profile(archive, {'children': [{'id': 'a', 'alias': '示例'}],
                    'timezone': 'UTC', 'onboarding': {'acknowledged': True,
                    'decisions': {'age': 'deferred', 'school': 'deferred'}}}, True)
                before = (archive/'FAMILY-profile.json').read_bytes()
                patch = archive/'patch.json'
                patch.write_text(json.dumps({'onboarding': {'decisions': {'family_members': decision}}}), encoding='utf-8')
                result = subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).with_name('profile_store.py')),
                    'update', '--archive', str(archive), '--patch', str(patch), '--confirmed'], capture_output=True, encoding='utf-8')
                if result.returncode:
                    self.assertEqual((archive/'FAMILY-profile.json').read_bytes(), before)
                self.assertEqual(result.returncode, 0, result.stderr)
                saved = read_profile(archive)
                self.assertEqual(saved['onboarding']['decisions'], {'age': 'deferred', 'school': 'deferred', 'family_members': decision})
                self.assertEqual(saved['family_members'], [])
                self.assertEqual(saved['children'], first['children'])
                self.assertEqual(saved['family_id'], first['family_id'])
                self.assertEqual(saved['revision'], 2)
                self.assertEqual(len(saved['change_history']), 2)
                self.assertTrue(status(saved)['ready'])
                update_profile(archive, {'onboarding': {'decisions': {'family_members': 'declined'}}}, True)
                self.assertEqual(read_profile(archive)['revision'], 3)

    def test_top_level_member_lists_still_reject_scalars_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            update_profile(archive, {'children': [{'id': 'a'}]}, True)
            before = (archive/'FAMILY-profile.json').read_bytes()
            for key in ('children', 'family_members'):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    update_profile(archive, {key: 'declined'}, True)
                self.assertEqual((archive/'FAMILY-profile.json').read_bytes(), before)

    def test_id_merges_and_child_school_history_remain_intact(self):
        old = {'children': [{'id': 'a', 'alias': '甲', 'school_baselines': [{'effective_date': '2030-01-01', 'grade_index': 1}]},
                            {'id': 'b', 'alias': '乙'}], 'family_members': [{'id': 'adult-a', 'role': '家长'}]}
        patch = {'children': [{'id': 'a', 'school_baselines': [{'effective_date': '2031-01-01', 'grade_index': 2}]}],
                 'family_members': [{'id': 'adult-a', 'alias': '示例家长'}]}
        before = deepcopy((old, patch))
        saved = merge(old, patch)
        self.assertEqual([r['effective_date'] for r in saved['children'][0]['school_baselines']], ['2030-01-01', '2031-01-01'])
        self.assertEqual(saved['children'][1], old['children'][1])
        self.assertEqual(saved['family_members'], [{'id': 'adult-a', 'role': '家长', 'alias': '示例家长'}])
        self.assertEqual((old, patch), before)

    def test_same_named_custom_keys_are_not_schema_lists(self):
        old = {'custom': {'family_members': 'before', 'children': 'before', 'school_baselines': 'before'}}
        patch = {'custom': {'family_members': 'after', 'children': 'after', 'school_baselines': 'after'}}
        self.assertEqual(merge(old, patch), patch)


if __name__ == '__main__':
    unittest.main()
