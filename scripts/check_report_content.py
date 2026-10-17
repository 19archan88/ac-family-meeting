"""Check the meeting-audit delivery contract, not the truth of its evidence."""
import argparse
import json
from pathlib import Path
import re

TITLE = '会议内容审计评估报告'
HEADERS = ['原话或观点定位', '校准与可用表达']


def visible_lines(markdown):
    """Ignore fenced examples and comments so they cannot satisfy the contract."""
    markdown = re.sub(r'<!--.*?-->', '', markdown, flags=re.S)
    fence = None
    for line in markdown.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if fence:
            if re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*', line):
                fence = None
            continue
        if match:
            fence = match[1]
            continue
        yield line


def cells(line):
    value = line.strip()
    if not value.startswith('|') or not value.endswith('|'):
        return None
    return [v.strip() for v in re.split(r'(?<!\\)\|', value[1:-1])]


def validate_audit(markdown, required=True):
    lines = list(visible_lines(markdown))
    starts = [i for i, line in enumerate(lines)
              if re.fullmatch(r'##\s+(?:🌈\s*)?' + TITLE + r'\s*', line)]
    if not starts and not required:
        return {'audit': 'not_required_for_this_report'}
    if len(starts) != 1:
        raise ValueError('内容审计：须保留且仅保留一个二级标题“' + TITLE + '”。')
    start = starts[0] + 1
    end = next((i for i in range(start, len(lines)) if re.match(r'^#{1,2}\s', lines[i])), len(lines))
    section = lines[start:end]
    if any(line.lstrip().startswith('|') and cells(line) is None for line in section):
        raise ValueError('内容审计：表格行必须保留首尾竖线，不能遗漏证据行。')
    rows = [(i, cells(line)) for i, line in enumerate(section) if cells(line) is not None]
    if not rows:
        body = '\n'.join(section)
        if '本次未发现需校准的观点。' in body:
            return {'audit': 'no_findings', 'semantic_review': 'required'}
        if re.search(r'材料不足，无法完成内容审计：\S+', body):
            return {'audit': 'insufficient_material', 'semantic_review': 'required'}
        raise ValueError('内容审计：须提供审计表，或如实说明没有发现／材料不足及原因。')
    if rows[0][1] != HEADERS:
        raise ValueError('内容审计表头须为：' + ' | '.join(HEADERS))
    if len(rows) < 3 or rows[1][0] != rows[0][0] + 1 or any(not re.fullmatch(r':?-{3,}:?', c) for c in rows[1][1]) or len(rows[1][1]) != 2:
        raise ValueError('内容审计：表格须有两列分隔行和至少一个证据条目。')
    for index, (line_number, row) in enumerate(rows[2:], 1):
        if line_number != rows[1][0] + index or len(row) != 2 or not all(row):
            raise ValueError(f'内容审计第 {index} 项：须为连续的完整两列表格。')
        evidence = re.fullmatch(r'(原话|概括)：(.+?)；说话人：(.+?)；定位：(.+)', row[0])
        if not evidence or not all(part.strip() for part in evidence.groups()):
            raise ValueError(f'内容审计第 {index} 项：区分原话／概括，并填写说话人与定位；未知须明示。')
        location = evidence[4]
        if not re.search(r'\d{1,3}[:：][0-5]\d|第\s*\d+\s*段|时间未提供|时间无法确定', location):
            raise ValueError(f'内容审计第 {index} 项：提供时间戳或段落；缺失时间须明示，不能编造。')
    return {'audit': 'passed', 'rows': len(rows) - 2, 'semantic_review': 'required'}


def check_report(source, audience='parent'):
    source = Path(source)
    # Aggregates and separately requested family/guide artifacts have other schemas.
    # Unknown filenames default to a parent meeting report; do not bypass the gate
    # simply by calling a new weekly report "report.md".
    aggregate = source.stem.startswith(('FM-M-', 'FM-S-', 'FM-Y-'))
    required = audience == 'parent' and not aggregate and not source.stem.endswith('-minutes')
    return validate_audit(source.read_text(encoding='utf-8-sig'), required=required)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--audience', choices=('parent', 'family', 'guide'), default='parent')
    args = parser.parse_args()
    print(json.dumps(check_report(args.source, args.audience), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
