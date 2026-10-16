"""Custom school calendars and portable license notices."""
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from meeting_context import period_context
from build_report_html import build, ROOT


class PublicPackageTests(unittest.TestCase):
    def test_custom_semester_boundaries_and_unknown_periods(self):
        semesters = [{'key': '2030-term-1', 'start': '2030-01-10', 'end': '2030-04-20'},
                     {'key': '2030-term-2', 'start': '2030-05-10', 'end': '2030-08-20'}]
        original = json.dumps(semesters)
        self.assertIsNone(period_context(date(2030, 1, 9), semesters)['semester'])
        self.assertEqual(period_context(date(2030, 1, 10), semesters)['semester']['key'], '2030-term-1')
        self.assertEqual(period_context(date(2030, 4, 20), semesters)['semester']['key'], '2030-term-1')
        self.assertIsNone(period_context(date(2030, 4, 21), semesters)['semester'])
        self.assertEqual(period_context(date(2030, 8, 1), semesters)['semester']['key'], '2030-term-2')
        self.assertIsNone(period_context(date(2030, 8, 1), [])['summer_outside_semester'])
        self.assertEqual(json.dumps(semesters), original)
        with self.assertRaises(ValueError):
            period_context(date(2030, 1, 1), semesters + [dict(semesters[0])])
        with self.assertRaises(ValueError):
            period_context(date(2030, 1, 1), semesters + [
                {'key': 'overlap', 'start': '2030-04-20', 'end': '2030-05-11'}])

    def test_cli_uses_custom_family_calendar(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'FAMILY-profile.json'
            profile.write_text(json.dumps({'children': [{'id': 'a'}], 'semesters': [
                {'key': 'summer-term', 'start': '2030-08-01', 'end': '2030-08-31'}]}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/meeting_context.py'),
                                     '2030-08-10', '--profile', str(profile)], capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout.decode('utf-8'))['period']['semester']['key'], 'summer-term')

    def test_html_preserves_complete_notices_and_original(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'FM-2030-001-2030-05-17.md'
            raw = '# 虚构会议\n\n仅验证许可打包。'
            source.write_text(raw, encoding='utf-8')
            result = build(source).read_text(encoding='utf-8')
            block = re.search(r'id="ac-family-license-notices">(.*?)</script>', result, re.S)
            notices = json.loads(block.group(1))
            self.assertEqual(len(notices), 4)
            for filename, content in notices.items():
                self.assertEqual(content, (ROOT / filename).read_text(encoding='utf-8'))
            self.assertEqual(source.read_text(encoding='utf-8'), raw)


if __name__ == '__main__':
    unittest.main()
