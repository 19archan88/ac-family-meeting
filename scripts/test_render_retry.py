"""Exercise public CLI retries, interrupted rendering and private cache boundaries."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from build_report_html import build, ROOT
from render_retry import render

FAMILY = ROOT.name == 'ac-family-meeting'
ALLOWED = ('parent', 'family', 'guide') if FAMILY else ('parent', 'child')
SECOND_AUDIENCE = 'family' if FAMILY else 'child'


class RenderRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/('FM-2030-001-2030-05-17.md' if FAMILY else 'D-2030-05-17.md')
        self.source.write_text('# 虚构标题\n\n完整正文。', encoding='utf-8')
        self.html = self.source.with_suffix('.html')
        self.receipt = self.root/'.qa'/(self.html.name+'.render.json')

    def generate(self, **kwargs):
        return render(build, self.source, allowed=ALLOWED, **kwargs)

    def settings(self):
        return json.loads(re.search(r'<script id="report-settings" type="application/json">(.*?)</script>',
                                   self.html.read_text(encoding='utf-8'), re.S)[1])

    def cli(self, script, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts'/script), *map(str, args)],
                              capture_output=True, encoding='utf-8')

    def test_public_cli_retries_preserve_options(self):
        scripts = ['build_report_html.py'] if FAMILY else ['build_report_html.py', 'prepare_report.py']
        for script in scripts:
            flags = ['--temporary', '--onboarding-acknowledged'] if script == 'prepare_report.py' else []
            for options in (['--headline', '保持原提要', '--audience', SECOND_AUDIENCE], []):
                result = self.cli(script, self.source, *flags, *options)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.settings()['headline'], '保持原提要')
            self.assertEqual(self.settings()['audience'], SECOND_AUDIENCE)
            self.assertTrue(json.loads(self.receipt.read_text(encoding='utf-8'))['html_reused'])

    def test_unchanged_render_is_reused_without_calling_builder(self):
        self.generate(headline='原提要', audience=SECOND_AUDIENCE)
        raw = self.html.read_bytes()
        with patch('build_report_html.build', side_effect=AssertionError('unexpected build')) as builder:
            render(builder, self.source, allowed=ALLOWED)
        self.assertEqual(self.html.read_bytes(), raw)

    def test_failed_first_build_preserves_parameters(self):
        with patch('build_report_html.build', side_effect=OSError('disk full')) as builder:
            with self.assertRaises(OSError):
                render(builder, self.source, headline='首次失败', audience=SECOND_AUDIENCE, allowed=ALLOWED)
        self.assertFalse(self.html.exists())
        self.generate()
        self.assertEqual(self.settings()['headline'], '首次失败')
        self.assertEqual(self.settings()['audience'], SECOND_AUDIENCE)

    def test_missing_template_resources_do_not_lose_choices(self):
        with patch('render_retry.fingerprint', side_effect=FileNotFoundError('missing template')):
            with self.assertRaises(OSError):
                self.generate(headline='资源修好后保留', audience=SECOND_AUDIENCE)
        self.assertEqual(json.loads(self.receipt.read_text(encoding='utf-8'))['status'], 'failed')
        self.generate()
        self.assertEqual(self.settings()['headline'], '资源修好后保留')
        self.assertEqual(self.settings()['audience'], SECOND_AUDIENCE)

    def test_failed_explicit_change_does_not_reuse_old_html(self):
        self.generate(headline='旧提要')
        with patch('build_report_html.build', side_effect=OSError('disk full')) as builder:
            with self.assertRaises(OSError):
                render(builder, self.source, headline='新提要', allowed=ALLOWED)
        self.assertEqual(self.settings()['headline'], '旧提要')
        self.generate()
        self.assertEqual(self.settings()['headline'], '新提要')

    def test_deleted_or_changed_html_is_rebuilt_with_saved_choices(self):
        self.generate(headline='恢复提要')
        self.html.unlink()
        self.generate()
        self.assertEqual(self.settings()['headline'], '恢复提要')
        self.html.write_text('损坏页面', encoding='utf-8')
        self.generate()
        self.assertEqual(self.settings()['headline'], '恢复提要')

    def test_template_change_rebuilds(self):
        self.generate(headline='模板更新')
        with patch('render_retry.fingerprint', return_value='new'), patch('build_report_html.build', wraps=build) as builder:
            render(builder, self.source, allowed=ALLOWED)
            builder.assert_called_once()
        self.assertEqual(self.settings()['headline'], '模板更新')

    def test_existing_legacy_html_recovers_display_choices(self):
        build(self.source, headline='旧页面提要', audience=SECOND_AUDIENCE)
        self.assertFalse(self.receipt.exists())
        self.generate()
        self.assertEqual(self.settings()['headline'], '旧页面提要')
        self.assertEqual(self.settings()['audience'], SECOND_AUDIENCE)

    def test_changed_source_does_not_inherit_unreviewed_old_headline(self):
        self.generate(headline='只适用于旧正文', audience=SECOND_AUDIENCE)
        self.source.write_text('# 新正文标题\n\n另一份内容。', encoding='utf-8')
        self.generate()
        self.assertEqual(self.settings()['headline'], '新正文标题')
        self.assertEqual(self.settings()['audience'], 'parent')

    def test_corrupt_receipt_does_not_overwrite_html(self):
        self.generate(headline='保留')
        original = self.html.read_bytes()
        self.receipt.write_text('{bad json', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.generate()
        self.assertEqual(self.html.read_bytes(), original)

    def test_expected_cli_errors_are_concise_and_nonzero(self):
        archive = self.root/'archive'
        bad_patch = self.root/'bad.json'
        bad_patch.write_text('{bad json', encoding='utf-8')
        commands = [('build_report_html.py', [self.root/'missing.md']),
                    ('profile_store.py', ['update', '--archive', archive, '--patch', bad_patch, '--confirmed'])]
        if FAMILY:
            commands += [('check_report_content.py', [self.source]),
                         ('deliver_report.py', ['finish', self.source, '--receipt', self.root/'missing.json'])]
        else:
            commands += [('prepare_report.py', [self.source])]
        for script, args in commands:
            with self.subTest(script=script):
                result = self.cli(script, *args)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('Traceback', result.stderr)
                self.assertTrue(result.stderr.strip())
        self.assertFalse(self.html.exists())

    @unittest.skipIf(FAMILY, 'Only bedtime has prepare_report')
    def test_cached_page_does_not_bypass_onboarding(self):
        from prepare_report import prepare
        prepare(self.source, temporary=True, acknowledged=True, headline='临时报告')
        with self.assertRaises(ValueError):
            prepare(self.source, archive=self.root/'unconfigured')
        self.assertEqual(self.settings()['headline'], '临时报告')

    def test_unexpected_programming_error_is_not_hidden(self):
        from cli_support import run_cli
        def broken():
            raise RuntimeError('unexpected defect')
        with self.assertRaises(RuntimeError):
            run_cli(broken)


if __name__ == '__main__':
    unittest.main()
