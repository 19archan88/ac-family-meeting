"""Check actual HTML script boundaries, not just independent JS source files."""
from html.parser import HTMLParser
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from build_report_html import build, ROOT


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.current = [dict(attrs), '']

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.blocks.append(self.current)
            self.current = None


class GeneratedHTMLTests(unittest.TestCase):
    def test_final_scripts_and_licenses_are_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'D-2030-05-17.md'
            source.write_text('# 虚构测试\n\n## 内容\n完整正文。', encoding='utf-8')
            page = build(source).read_text(encoding='utf-8')
            parsed = Scripts(); parsed.feed(page)
            executable = [body for attrs, body in parsed.blocks if attrs.get('type') != 'application/json']
            self.assertEqual(len(executable), 4)
            expected = ['vendor/marked.umd.js', 'vendor/html2canvas.min.js', 'png-encoder.js', 'report.js']
            for body, name in zip(executable, expected):
                self.assertEqual(body, (ROOT/'assets/web'/name).read_text(encoding='utf-8'))
                checked = subprocess.run(['node', '--check'], input=body, text=True, encoding='utf-8', capture_output=True)
                self.assertEqual(checked.returncode, 0, checked.stderr[-1000:])
            notices = [json.loads(body) for attrs, body in parsed.blocks if attrs.get('id', '').endswith('license-notices')]
            self.assertEqual(len(notices), 1)
            self.assertEqual(notices[0]['LICENSE'], (ROOT/'LICENSE').read_text(encoding='utf-8'))
            self.assertIn('<html lang="zh-CN" data-report-ready="true">', executable[-1])


    def test_windows_line_endings_and_template_text(self):
        import base64
        import html
        import re
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'D-2030-05-17.md'
            raw = b'\xef\xbb\xbf' + '# 虚构测试\r\nprompt_version: v2.0\r\n\r\n## 内容\r\n完整原文 @@LICENSES@@ </script> & 保留。\r\n'.encode('utf-8')
            source.write_bytes(raw)
            page = build(source).read_text(encoding='utf-8')
            fallback = html.unescape(re.search(r'id="static-fallback"[^>]*><pre>(.*?)</pre>', page, re.S)[1])
            self.assertEqual(fallback, raw.decode('utf-8-sig').replace('\r\n', '\n'))
            parsed = Scripts(); parsed.feed(page)
            settings = next(json.loads(body) for attrs, body in parsed.blocks if attrs.get('id') == 'report-settings')
            self.assertEqual(base64.b64decode(settings['markdownBase64']), raw)
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(len([1 for attrs, _ in parsed.blocks if attrs.get('id', '').endswith('license-notices')]), 1)


if __name__ == '__main__':
    unittest.main()
