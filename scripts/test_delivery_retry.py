"""Retry must preserve presentation choices and avoid unnecessary rebuilds."""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_delivery as fixtures
from deliver_report import finish, read_json, atomic_json


class RetryTests(unittest.TestCase):
    setUp = fixtures.DeliveryTests.setUp
    tearDown = fixtures.DeliveryTests.tearDown
    def settings(self):
        page = self.source.with_suffix('.html').read_text(encoding='utf-8')
        return json.loads(re.search(r'<script id="report-settings" type="application/json">(.*?)</script>', page, re.S)[1])

    def test_completed_retry_keeps_choices_and_reuses_html(self):
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True,
               headline='保留这句提要', audience='family')
        original = self.source.with_suffix('.html').read_bytes()
        with patch('deliver_report.build', side_effect=AssertionError('unexpected rebuild')):
            finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
        self.assertEqual(self.source.with_suffix('.html').read_bytes(), original)
        self.assertEqual(self.settings()['audience'], 'family')
        self.assertEqual(self.settings()['headline'], '保留这句提要')

    def test_build_failure_remembers_choices_before_any_html_exists(self):
        with patch('deliver_report.build', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True,
                       headline='失败后仍保留', audience='family')
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
        self.assertEqual(self.settings()['headline'], '失败后仍保留')
        self.assertEqual(self.settings()['audience'], 'family')

    def test_explicit_change_and_missing_html_rebuild_with_saved_choices(self):
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True, headline='第一版')
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True, headline='主动修订')
        self.assertEqual(self.settings()['headline'], '主动修订')
        self.source.with_suffix('.html').unlink()
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
        self.assertEqual(self.settings()['headline'], '主动修订')

    def test_legacy_receipt_recovers_matching_html_options(self):
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True,
               headline='旧回执提要', audience='family')
        receipt = read_json(self.receipt)
        for key in ('render_options', 'renderer_sha256', 'html_sha256'):
            receipt.pop(key, None)
        atomic_json(self.receipt, receipt)
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
        self.assertEqual(self.settings()['headline'], '旧回执提要')
        self.assertEqual(self.settings()['audience'], 'family')

    def test_cli_validation_error_is_concise(self):
        bad = self.root/'invalid.md'
        bad.write_text('# 缺审计模块', encoding='utf-8')
        result = subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).with_name('check_report_content.py')), str(bad)],
                                capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        self.assertIn('内容审计', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_archive_failure_reuses_verified_html_on_retry(self):
        with patch('deliver_report.commit', side_effect=OSError('temporary failure')):
            with self.assertRaises(OSError):
                finish(self.source, self.receipt, self.state, self.patch_file,
                       family_archive=self.archive, headline='归档失败不丢提要')
        with patch('deliver_report.build', side_effect=AssertionError('unexpected rebuild')):
            finish(self.source, self.receipt, self.state, self.patch_file, family_archive=self.archive)
        self.assertEqual(self.settings()['headline'], '归档失败不丢提要')
        self.assertEqual(len(read_json(self.state)['meetings']), 2)

    def test_renderer_change_rebuilds_but_keeps_choices(self):
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True, headline='模板升级保留')
        from build_report_html import build
        with patch('deliver_report.renderer_digest', return_value='new-template'), patch('deliver_report.build', wraps=build) as rebuild:
            finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
            rebuild.assert_called_once()
        self.assertEqual(self.settings()['headline'], '模板升级保留')

    def test_failed_explicit_change_cannot_reuse_the_old_page(self):
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True, headline='旧提要')
        with patch('deliver_report.build', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True, headline='新提要')
        self.assertEqual(self.settings()['headline'], '旧提要')
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
        self.assertEqual(self.settings()['headline'], '新提要')

    def test_cli_retry_omits_arguments_without_resetting_them(self):
        script = str(Path(__file__).with_name('deliver_report.py'))
        command = [sys.executable, '-X', 'utf8', script, 'finish', str(self.source),
                   '--receipt', str(self.receipt), '--no-archive', '--onboarding-acknowledged']
        for extra in (['--headline', 'CLI保留', '--audience', 'family'], []):
            result = subprocess.run(command + extra, capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.settings()['headline'], 'CLI保留')
        self.assertEqual(self.settings()['audience'], 'family')
        self.assertTrue(read_json(self.receipt)['html_reused'])

    def test_legacy_missing_html_requires_explicit_options(self):
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True, headline='历史提要')
        receipt = read_json(self.receipt)
        receipt.pop('render_options')
        atomic_json(self.receipt, receipt)
        self.source.with_suffix('.html').unlink()
        with self.assertRaisesRegex(ValueError, '旧回执'):
            finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True)
        self.assertFalse(self.source.with_suffix('.html').exists())
        finish(self.source, self.receipt, no_archive=True, onboarding_acknowledged=True,
               headline='找回的历史提要', audience='parent')
        self.assertEqual(self.settings()['headline'], '找回的历史提要')
