/* Maintainer DOM integration tests. No browser, layout engine, or network fetch. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '..');
const family = path.basename(root) === 'ac-family-meeting';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ac-presentation-'));
let count = 0;

function openPage(page, render = true) {
  const dom = new JSDOM(page, {runScripts: 'outside-only'});
  const w = dom.window;
  w.TextDecoder = TextDecoder;
  if (render) {
    const scripts = [...w.document.scripts].filter(s => s.type !== 'application/json');
    assert.equal(scripts.length, 4, 'final HTML must retain all executable script boundaries');
    w.eval(scripts[0].textContent); // The shipped Marked library.
    w.eval(scripts[3].textContent); // The actual embedded presentation script.
    assert.equal(w.document.documentElement.dataset.reportReady, 'true');
  }
  return dom;
}

function build(name, md, audience = 'parent') {
  const source = path.join(temp, name + '.md');
  fs.writeFileSync(source, md);
  const result = spawnSync(process.env.PYTHON || 'python',
    ['-X', 'utf8', path.join(root, 'scripts/build_report_html.py'), source, '--audience', audience],
    {encoding:'utf8'});
  assert.equal(result.status, 0, result.stderr || result.error?.message);
  return fs.readFileSync(source.slice(0,-3) + '.html', 'utf8');
}

function checkSource(doc, md) {
  const config = JSON.parse(doc.getElementById('report-settings').textContent);
  assert.equal(Buffer.from(config.markdownBase64,'base64').toString('utf8'), md);
  assert.equal(doc.getElementById('static-fallback').textContent, md.replace(/\r\n?/g,'\n'));
  assert.equal(doc.getElementById('save-markdown').getAttribute('href'),
    `data:text/markdown;charset=utf-8;base64,${config.markdownBase64}`);
  assert.equal(doc.querySelectorAll('#toc a').length, doc.querySelectorAll('#chapters > section').length);
  for (const link of doc.querySelectorAll('#toc a')) assert.ok(doc.querySelector(link.hash));
}

const periods = family ? [
  ['FM-2030-006-2030-05-19','本周的注脚','parent'],
  ['FM-M-2030-05','本月的注脚','parent'],
  ['FM-S-2030-term-3','本学期的注脚','parent'],
  ['FM-Y-2030','这一年的注脚','parent'],
  ['FM-2030-PENDING-2030-05-19','本周的注脚','family'],
  ['guide','阅读提要','guide'],
  ['FM-M-2030-05-guide','阅读提要','guide'],
] : [
  ['D-2030-05-17','今夜的注脚','parent'],
  ['W-2030-W20','本周的注脚','parent'],
  ['M-2030-05','本月的注脚','parent'],
  ['Y-2030-A','这一年的注脚','parent'],
  ['Y-2030-B','这一年的注脚','child'],
  ['guide','阅读提要','parent'],
];

try {
  for (const [name, label, audience] of periods) {
    // No daily/weekly-specific section names: every period must retain ordinary content.
    const md = '# 虚构结构测试\n\nprompt_version: v2.0  \n材料范围：本期可见记录\n\n**提要重点。** 保留限定条件。\n\n## 本期记录\n\n普通段落与**行内强调**、*斜体*、`代码`。\n\n3. 顺序甲\n4. 顺序乙\n   - 嵌套甲\n   - 嵌套乙\n\n### 一个议题\n\n**依据：** 只来自材料。\n\n#### 一段细节\n\n> 原话保留。\n\n| 字段 | 记录 |\n|---|---|\n| 项目 | **重点值** |\n\n[来源](https://example.org/evidence)\n';
    const page = build(name, md, audience);
    const dom = openPage(page), doc = dom.window.document;
    checkSource(doc, md);
    assert.equal(doc.querySelector('.reading-lead').dataset.label, label, name);
    assert.equal(doc.querySelectorAll('.detail-line').length, 2);
    assert.equal(doc.querySelector('#chapters ol').start, 3);
    assert.equal(doc.querySelectorAll('#chapters ol ul li').length, 2);
    assert.ok(doc.querySelector('.subsection .topic blockquote'));
    for (const selector of ['strong','em','code','table','a[href="https://example.org/evidence"]'])
      assert.ok(doc.querySelector('#chapters ' + selector), selector);
    assert.equal(dom.window.getComputedStyle(doc.getElementById('static-fallback')).display,'none');
    dom.window.close();
    const fallback = openPage(page, false);
    assert.notEqual(fallback.window.getComputedStyle(fallback.window.document.getElementById('static-fallback')).display,'none');
    assert.equal(fallback.window.getComputedStyle(fallback.window.document.getElementById('chapters')).display,'none');
    assert.equal(fallback.window.getComputedStyle(fallback.window.document.querySelector('.export-actions')).display,'none');
    fallback.window.close();
    count++;
  }

  const quoteHeading = family ? '金句与温暖瞬间' : '今日金句';
  const actionHeading = family ? '父母行动' : '姿态建议';
  const md = `# 虚构边界测试\n\n## ${quoteHeading}\n\n- **单独原话。**\n- **带解释原话。** 解释中的*强调*与\`代码\`。\n- 开头是正文，**后半加粗。** 不应自动拆分。\n\n## ${actionHeading}\n\n3. **行动甲。** 保留起始编号。\n   1. 内层甲\n   2. 内层乙\n4. 行动乙\n\n## 对话记录\n\n| 片段 | 内容 | 说明 |\n|---|---|---|\n| **未提供时间**与*补充* | **正文** | 未知 |\n| 00:02–00:08 标题 | 第二段 | 标签 |\n`;
  const dom = openPage(build(family ? 'FM-2030-009-2030-05-20' : 'D-2030-05-20', md));
  const doc=dom.window.document;
  checkSource(doc,md);
  const quotes=doc.querySelectorAll('.quotes > ul > li');
  assert.equal(quotes.length,3);
  assert.equal(doc.querySelectorAll('.split-quote').length,family ? 0 : 1);
  assert.equal(quotes[0].textContent,'单独原话。');
  assert.ok(quotes[2].textContent.includes('开头是正文，后半加粗。'));
  assert.ok(quotes[1].querySelector('em'));
  const actions=doc.querySelector('.posture > ol');
  assert.equal(actions.style.counterReset,'posture 2');
  assert.equal(actions.querySelector('ol').style.counterReset,'');
  if (family) {
    assert.equal(doc.querySelector('tbody td').dataset.label,'片段');
    assert.equal(doc.querySelectorAll('.timeline').length,0);
  } else {
    assert.equal(doc.querySelectorAll('.timeline .moment').length,2);
    assert.ok(doc.querySelector('.without-time .moment-title strong'));
    assert.ok(doc.querySelector('.without-time .moment-title em'));
    assert.equal(doc.querySelector('.moment time').textContent,'00:02–00:08');
  }
  dom.window.close(); count++;

  for (const [suffix, body] of [
    ['sparse', '材料缺失，暂不形成统计。'],
    ['long', '## 长记录\n\n| 序号 | 文字 |\n|---|---|\n' + Array.from({length:120},(_,i)=>`| ${i+1} | 完整记录${i+1} |`).join('\n')],
    ['unsafe', '## 原文\n\n<script>window.injection=1</script>\n\n[无效链接](javascript:alert(1))\n\n末尾保留。'],
  ]) {
    const raw='# 虚构测试\n\n'+body;
    const dom=openPage(build((family ? 'FM-M-2030-05-' : 'M-2030-05-')+suffix,raw));
    const doc=dom.window.document;
    checkSource(doc,raw);
    assert.equal(dom.window.injection,undefined);
    assert.equal(doc.querySelectorAll('#chapters script, #chapters a[href^="javascript:"]').length,0);
    if(suffix==='long') {
      assert.equal(doc.querySelectorAll('#chapters tbody tr').length,120);
      assert.ok(doc.querySelector('#chapters').textContent.includes('完整记录120'));
    }
    if(suffix==='sparse') assert.ok(doc.querySelector('#opening').textContent.includes(body));
    dom.window.close(); count++;
  }

  // Examples are complete artifacts, not mandatory formatting templates for other periods.
  for (const filename of fs.readdirSync(path.join(root,'examples')).filter(x=>x.endsWith('.md'))) {
    const md=fs.readFileSync(path.join(root,'examples',filename),'utf8');
    const page=fs.readFileSync(path.join(root,'examples',filename.slice(0,-3)+'.html'),'utf8');
    const dom=openPage(page);
    checkSource(dom.window.document,md);
    assert.ok(dom.window.document.querySelector('#chapters').textContent.trim().length>100);
    dom.window.close(); count++;
  }
  console.log(`PASS ${count} generated-page cases: periods, source roundtrip, headings, lists, tables, fallback and content safety. Layout/PDF/PNG not simulated.`);
} finally {
  // Remove only the unique temporary directory created by this test.
  assert.equal(path.dirname(temp), fs.realpathSync(os.tmpdir()));
  assert.ok(path.basename(temp).startsWith('ac-presentation-'));
  fs.rmSync(temp, {recursive:true, force:true});
}
