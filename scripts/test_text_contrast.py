"""Contrast checks for information text against the template's solid surfaces.

These checks do not simulate layout, antialiasing, printing or image export.
"""
from pathlib import Path
import re
import unittest


def luminance(value):
    value = value.lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    rgb = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)


class InformationTextContrastTests(unittest.TestCase):
    def test_small_text_on_actual_solid_surfaces(self):
        css = (Path(__file__).resolve().parents[1] / 'assets/web/report.css').read_text(encoding='utf-8')
        variables = dict(re.findall(r'(--[\w-]+):([^;}]+)', css))

        def resolve(value):
            match = re.fullmatch(r'var\((--[\w-]+)\)', value)
            return variables[match[1]] if match else value

        for selector, background in [('.side-label', '--back'), ('.sidebar nav a.active span', '--back'),
                                     ('.cover-top span:first-child', '--paper'), ('.eyebrow', '--paper'),
                                     ('.chapter-number', '--paper'), ('.chapter li::marker', '--paper'),
                                     ('.chapter li::marker', '--surface-light'), ('.chapter li::marker', '--surface-white')]:
            with self.subTest(selector=selector, background=background):
                blocks = re.findall(re.escape(selector) + r'\{([^{}]+)\}', css)
                colors = [m[1] for block in blocks if (m := re.search(r'(?:^|;)color:([^;]+)', block))]
                self.assertTrue(colors, selector)
                self.assertGreaterEqual(contrast(resolve(colors[0]), variables[background]), 4.5)


if __name__ == '__main__':
    unittest.main()
