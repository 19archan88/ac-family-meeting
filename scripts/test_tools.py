import base64, json, tempfile, unittest, re
from pathlib import Path
from datetime import date
from meeting_context import inspect, period_context
from build_report_html import build

class MeetingChecks(unittest.TestCase):
 def test_calendar_boundaries(self):
  self.assertIsNone(inspect('2015-01-01')['child']['age'])
  self.assertEqual(inspect('2030-04-11',birth=date(2023,4,12))['child']['age_label'],'6岁11个月')
  self.assertEqual(inspect('2030-04-12',birth=date(2023,4,12))['child']['age_label'],'7岁0个月')
  self.assertFalse(inspect('2029-08-19',school_start=date(2029,8,20))['child']['school']['enrolled'])
  self.assertEqual(inspect('2029-08-20',school_start=date(2029,8,20))['child']['school']['elapsed']['total_days'],0)
  self.assertEqual(period_context(date(2027,1,31))['semester']['key'],'2026-2027-upper')
  self.assertEqual(period_context(date(2027,2,1))['semester']['key'],'2027-lower')
  self.assertIsNone(period_context(date(2026,8,1))['semester'])
  self.assertEqual(inspect('2026-10-03')['period']['month'],'2026-10')
 def test_duplicates_sequence_and_readonly(self):
  state={'meetings':[{'id':'one','date':'2026-09-18','number':1,'source_sha256':'abc'}]}
  before=json.dumps(state)
  result=inspect('2026-09-18',state,1,'abc')
  self.assertTrue(any('指纹' in w for w in result['warnings']))
  self.assertTrue(any('同日' in w for w in result['warnings']))
  self.assertTrue(inspect('2026-09-11',state,2)['requires_review'])
  self.assertTrue(inspect('2026-09-25',state,4)['requires_review'])
  self.assertFalse(inspect('2026-09-25',state,2)['requires_review'])
  self.assertEqual(inspect('2027-01-01',state,1)['expected_next_visible_number'],1)
  self.assertEqual(json.dumps(state),before)
  self.assertIsNone(result['month_index'])
 def test_invalid_and_sparse(self):
  for day in ['2026-02-30','2026/09/18']:
   with self.assertRaises(ValueError):inspect(day)
  self.assertTrue(inspect('2026-09-18')['requires_review'])
  with self.assertRaises(ValueError):inspect('2026-09-18',number=0)
  with self.assertRaises(ValueError):inspect('2026-09-18',{'meetings':[{'id':'bad'}]})
 def test_html_roundtrip_and_no_state_mutation(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'FM-2026-001-2026-09-18.md'
   original=b'\xef\xbb\xbf'+ '# 标题\nprompt_version: v2.0\n\n## 内容\n原话 </script> & 引用\n'.encode()
   p.write_bytes(original); output=build(p,audience='family'); html=output.read_text(encoding='utf-8')
   config=json.loads(re.search(r'<script id="report-settings" type="application/json">(.*?)</script>',html,re.S).group(1))
   self.assertEqual(base64.b64decode(config['markdownBase64']),original)
   self.assertEqual(p.read_bytes(),original)
   self.assertEqual(config['kind'],'会议纪要与双镜头分析')
   self.assertEqual(config['renderVersion'],'2.1.2')
   self.assertNotIn('@@',html)
   self.assertEqual(sorted(x.suffix for x in Path(td).iterdir()),['.html','.md'])
   with self.assertRaises(ValueError):build(p,p)
if __name__=='__main__': unittest.main()
