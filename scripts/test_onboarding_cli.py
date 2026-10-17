"""Use new processes to verify first-run gating, persisted replies and later updates."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT.name == 'ac-family-meeting'


class OnboardingCLITests(unittest.TestCase):
    def test_first_run_partial_then_later_save_across_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'private'
            archive.mkdir()
            stem = 'FM-2030-001-2030-05-17' if FAMILY else 'D-2030-05-17'
            source = archive / (stem + '.md')
            source.write_text('# 虚构测试\n\n## 会议内容审计评估报告\n\n本次未发现需校准的观点。\n', encoding='utf-8')
            receipt = Path(folder) / 'receipt.json'

            def run(script, *args):
                return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts'/script),
                                       *map(str, args)], capture_output=True, encoding='utf-8')

            def status():
                result = run('profile_store.py', 'status', '--archive', archive)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            def update(value):
                patch = Path(folder) / 'confirmed.json'
                patch.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                result = run('profile_store.py', 'update', '--archive', archive, '--patch', patch, '--confirmed')
                self.assertEqual(result.returncode, 0, result.stderr)

            if FAMILY:
                for args in [('start', '--receipt', receipt), ('ready', source, '--receipt', receipt)]:
                    result = run('deliver_report.py', *args)
                    self.assertEqual(result.returncode, 0, result.stderr)

            def deliver():
                if FAMILY:
                    return run('deliver_report.py', 'finish', source, '--receipt', receipt,
                               '--family-archive', archive, '--no-archive')
                return run('prepare_report.py', source, '--archive', archive)

            self.assertFalse(status()['ready'])
            self.assertNotEqual(deliver().returncode, 0)
            self.assertFalse(list(archive.rglob('*.html')))
            update({'children': [{'id': 'fictional-child', 'alias': '示例孩子'}]})
            self.assertIn('age', status()['unanswered'])
            self.assertNotEqual(deliver().returncode, 0)
            self.assertFalse(list(archive.rglob('*.html')))
            update({'timezone': 'UTC', 'family_members': [{'id': 'adult-a', 'role': '家长'}],
                    'onboarding': {'acknowledged': True, 'decisions': {'age': 'deferred', 'school': 'deferred'}}})
            self.assertTrue(status()['ready'])
            self.assertIn('age', status()['missing'])
            update({'children': [{'id': 'fictional-child', 'birth_date': '2023-01-01',
                                  'school_observation': {'as_of': '2030-05-17', 'label': '小学一年级'}}]})
            result = status()
            self.assertTrue(result['ready'])
            self.assertEqual(result['missing'], [])
            saved = json.loads((archive/'FAMILY-profile.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['children'][0]['alias'], '示例孩子')
            self.assertEqual(saved['children'][0]['birth_date'], '2023-01-01')
            self.assertEqual(saved['revision'], 3)
            result = deliver()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(list(archive.rglob('*.html')))
            self.assertFalse((archive/'STATE-latest.json').exists())


if __name__ == '__main__':
    unittest.main()
