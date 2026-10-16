"""Behavior tests with fictional family data, including CLI profile loading."""
from datetime import date
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from family_context import child_context, grade_context


def baseline(effective='2029-08-20', index=1, promotion='08-20'):
    return {'effective_date': effective, 'grade_index': index,
            'promotion_day': promotion,
            'stages': [{'name': '小学', 'years': 6}, {'name': '初中', 'years': 3},
                       {'name': '高中', 'years': 3}]}


class FamilyTests(unittest.TestCase):
    def test_custom_promotion_and_stage_transitions(self):
        rules = [baseline()]
        self.assertIsNone(grade_context(date(2029, 8, 19), rules))
        for when, expected in [('2029-08-20', '小学1年级'), ('2030-08-19', '小学1年级'),
                               ('2030-08-20', '小学2年级'), ('2035-08-20', '初中1年级'),
                               ('2038-08-20', '高中1年级')]:
            self.assertEqual(grade_context(date.fromisoformat(when), rules)['grade'], expected)
        self.assertIsNone(grade_context(date(2041, 8, 20), rules)['grade'])

    def test_original_september_rule_and_short_primary_system(self):
        rules = [baseline('2029-09-01', promotion='09-01')]
        self.assertEqual(grade_context(date(2030, 8, 31), rules)['grade'], '小学1年级')
        self.assertEqual(grade_context(date(2030, 9, 1), rules)['grade'], '小学2年级')
        rules[0]['stages'][0]['years'] = 5
        self.assertEqual(grade_context(date(2034, 9, 1), rules)['grade'], '初中1年级')

    def test_corrections_preserve_historical_results(self):
        rules = [baseline(), baseline('2031-08-20', 2)]  # Confirmed repeat.
        self.assertEqual(grade_context(date(2030, 8, 20), rules)['grade'], '小学2年级')
        self.assertEqual(grade_context(date(2031, 8, 20), rules)['grade'], '小学2年级')
        rules.append(baseline('2032-08-20', 5))  # Confirmed skip.
        self.assertEqual(grade_context(date(2032, 8, 20), rules)['grade'], '小学5年级')

    def test_age_reference_and_birthday_precedence(self):
        profile = {'age_reference': {'as_of': '2030-05-17', 'years': 7, 'months': 1}}
        result = child_context(date(2031, 5, 17), profile=profile)
        self.assertEqual(result['age_label'], '约8岁1个月')
        self.assertIsNone(child_context(date(2029, 5, 17), profile=profile)['age'])
        exact = child_context(date(2031, 5, 17), date(2023, 4, 12), profile=profile)
        self.assertEqual(exact['age_label'], '8岁1个月')
        self.assertEqual(exact['age_precision'], 'birth_date')

    def test_invalid_rules(self):
        for change in [{'promotion_day': '02-29'}, {'grade_index': 0}, {'stages': []}]:
            rule = baseline()
            rule.update(change)
            with self.assertRaises(ValueError):
                grade_context(date(2030, 1, 1), [rule])
        with self.assertRaises(ValueError):
            grade_context(date(2030, 1, 1), [baseline(), baseline()])

    def test_cli_selects_child_and_does_not_modify_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'FAMILY-profile.json'
            first = {'id': 'a', 'birth_date': '2023-04-12', 'school_start': '2029-08-20',
                     'school_baselines': [baseline()]}
            second = deepcopy(first)
            second['id'] = 'b'
            second['birth_date'] = '2024-04-12'
            path.write_text(json.dumps({'children': [first, second]}), encoding='utf-8')
            original = path.read_bytes()
            command = [sys.executable, str(Path(__file__).with_name('meeting_context.py')),
                       '2030-08-20', '--profile', str(path)]
            ambiguous = subprocess.run(command, capture_output=True)
            self.assertNotEqual(ambiguous.returncode, 0)
            result = subprocess.run(command + ['--child-id', 'b'], capture_output=True, check=True)
            data = json.loads(result.stdout.decode('utf-8'))
            self.assertEqual(data['child']['age_label'], '6岁4个月')
            self.assertEqual(data['child']['school']['grade'], '小学2年级')
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
