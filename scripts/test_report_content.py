"""Missing evidence must block delivery; unrelated report formats remain usable."""
from pathlib import Path
import tempfile
import unittest
from check_report_content import check_report, validate_audit

VALID = '''## 会议内容审计评估报告

| 原话或观点定位 | 校准与可用表达 |
| --- | --- |
| 概括：一次失败意味着不会；说话人：未确定（编号漂移）；定位：02:10—02:20 | 单次结果不能证明能力，可问“想换一种办法吗？” |
'''


class AuditContractTests(unittest.TestCase):
    def test_valid_and_explicit_unknown_evidence(self):
        self.assertEqual(validate_audit(VALID)['rows'], 1)
        value = VALID.replace('02:10—02:20', '时间未提供，来源第3段')
        self.assertEqual(validate_audit(value)['audit'], 'passed')
        self.assertEqual(validate_audit(VALID.replace('概括：', '原话：'))['audit'], 'passed')

    def test_missing_module_and_fenced_or_commented_fake_evidence(self):
        for value in ('# 报告', '```md\n' + VALID + '\n```', '<!--\n' + VALID + '\n-->'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_audit(value)

    def test_drift_missing_attribution_location_and_empty_response(self):
        for value in (VALID.replace('原话或观点定位', '观点与定位'),
                      VALID.replace('概括：', ''),
                      VALID.replace('；说话人：未确定（编号漂移）', ''),
                      VALID.replace('02:10—02:20', ''),
                      VALID.replace('02:10—02:20', '待填'),
                      VALID + '| 概括：遗漏的行\n',
                      VALID.replace('| --- | --- |', '\n| --- | --- |'),
                      VALID.replace('单次结果不能证明能力，可问“想换一种办法吗？”', ''),
                      VALID + '\n' + VALID):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_audit(value)

    def test_no_fabricated_findings_needed(self):
        self.assertEqual(validate_audit('## 会议内容审计评估报告\n本次未发现需校准的观点。')['audit'], 'no_findings')
        self.assertEqual(validate_audit('## 会议内容审计评估报告\n材料不足，无法完成内容审计：仅收到日期。')['audit'], 'insufficient_material')

    def test_other_periods_and_audiences_do_not_require_weekly_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, audience in [('FM-M-2030-05', 'parent'), ('FM-S-2030-term-1', 'parent'),
                                   ('FM-Y-2030', 'parent'), ('extract', 'family'), ('guide', 'guide')]:
                source = Path(folder) / (name + '.md')
                source.write_text('# 本期记录\n材料不足。', encoding='utf-8')
                self.assertEqual(check_report(source, audience)['audit'], 'not_required_for_this_report')
            source = Path(folder) / 'report.md'
            source.write_text('# 本次会议', encoding='utf-8')
            with self.assertRaises(ValueError):
                check_report(source)


if __name__ == '__main__':
    unittest.main()
