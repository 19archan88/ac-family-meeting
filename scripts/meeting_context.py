#!/usr/bin/env python3
"""Read-only meeting date, child context and duplicate/sequence checks. Standard library."""
import argparse, calendar, hashlib, json, re
from datetime import date
from pathlib import Path

from family_context import parse_date, child_context


def period_context(day, semesters=None):
    if semesters is not None:
        ranges=[]
        keys=set()
        for term in semesters:
            start,end=parse_date(term['start']),parse_date(term['end'])
            if end < start or not term.get('key') or term['key'] in keys:
                raise ValueError('Invalid or duplicate semester')
            keys.add(term['key'])
            ranges.append((start,end,term))
        ranges.sort(key=lambda value:value[0])
        for previous,current in zip(ranges,ranges[1:]):
            if current[0] <= previous[1]:
                raise ValueError('Semester ranges overlap')
        matches=[term for start,end,term in ranges if start <= day <= end]
        return {'month':day.strftime('%Y-%m'),'year':day.year,
                'semester':matches[0] if matches else None,
                'calendar_basis':'user_defined',
                'outside_configured_semesters':not bool(matches),
                'summer_outside_semester':None}

    if day.month >= 9:
        semester = {"key":f"{day.year}-{day.year+1}-upper", "start":f"{day.year}-09-01", "end":f"{day.year+1}-01-31"}
    elif day.month == 1:
        semester = {"key":f"{day.year-1}-{day.year}-upper", "start":f"{day.year-1}-09-01", "end":f"{day.year}-01-31"}
    elif day.month <= 7:
        semester = {"key":f"{day.year}-lower", "start":f"{day.year}-02-01", "end":f"{day.year}-07-31"}
    else:
        semester = None
    return {"month":day.strftime("%Y-%m"),"year":day.year,"semester":semester,"summer_outside_semester":day.month==8,"calendar_basis":"original_reference_requires_confirmation"}


def inspect(value, state=None, number=None, source_hash=None, birth=None, school_start=None, profile=None, semesters=None):
    day=parse_date(value)
    context=child_context(day,birth,school_start,profile)
    state=state or {}
    meetings=state.get('meetings',[])
    if not isinstance(meetings,list): raise ValueError('meetings must be a list')
    warnings=[]
    scope=state.get('numbering_scope','annual')
    if scope not in ('annual','continuous'): raise ValueError('Unknown numbering_scope')
    known=[]
    for m in meetings:
        if not isinstance(m,dict) or not m.get('id') or not m.get('date'): raise ValueError('Invalid meeting record')
        parse_date(m['date'])
        if m.get('number') is not None and (type(m['number']) is not int or m['number']<1): raise ValueError('Invalid historical number')
        known.append(m)
    if len({m['id'] for m in known}) != len(known): warnings.append('状态包含重复meeting_id，先修复历史索引')
    if number is not None and (type(number) is not int or number<1): raise ValueError('number must be a positive integer')
    if any(m['date']==value for m in known): warnings.append('同日已有会议：请确认修订还是另一场')
    if source_hash and any(m.get('source_sha256')==source_hash for m in known): warnings.append('来源指纹重复：请确认修订或重复提交')
    if known and value<max(m['date'] for m in known): warnings.append('日期倒退：请确认历史补录并核对后续归属')
    numbered=[m['number'] for m in known if m.get('number') is not None and (scope=='continuous' or m['date'][:4]==value[:4])]
    expected=max(numbered)+1 if numbered else 1
    if number is None: warnings.append('届数未提供：请确认实际届数，不以自然周推算')
    elif numbered and number!=expected: warnings.append(f'届数不连续：可见记录预计{expected}，收到{number}，请确认')
    if not known: warnings.append('缺少历史：本次只是可见档案起点，请确认届数与月内记录完整性')
    ids=[m['id'] for m in known if m['date'][:7]==value[:7]]
    return {'date':value,'date_confirmed_by_tool':False,'prompt_version':'v2.0',
            'period':period_context(day,semesters),'child':context,'numbering_scope':scope,
            'requested_number':number,'expected_next_visible_number':expected,
            'prior_visible_month_meetings':len(set(ids)),
            'month_index':None,'source_sha256':source_hash,'requires_review':bool(warnings),
            'warnings':warnings,'notice':'只读校验；不能证明日期已确认、历史完整、周期结束或报告已生成。'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('date');parser.add_argument('--state',type=Path);parser.add_argument('--number',type=int)
    parser.add_argument('--source',type=Path);parser.add_argument('--birth-date');parser.add_argument('--school-start')
    parser.add_argument('--profile',type=Path);parser.add_argument('--child-id')
    args=parser.parse_args()
    try:
        state=json.loads(args.state.read_text(encoding='utf-8-sig')) if args.state else None
        if state is not None and not isinstance(state,dict): raise ValueError('State must be an object')
        fingerprint=hashlib.sha256(args.source.read_bytes()).hexdigest() if args.source else None
        family={}; profile={}
        if args.profile:
            family=json.loads(args.profile.read_text(encoding='utf-8-sig'))
            children=family['children']
            ids=[c['id'] for c in children]
            if len(ids)!=len(set(ids)): raise ValueError('Child IDs must be unique')
            matches=[c for c in children if c['id']==args.child_id] if args.child_id else children
            if len(matches)!=1: raise ValueError('Select exactly one child with --child-id')
            profile=matches[0]
        elif args.child_id: raise ValueError('--child-id requires --profile')
        birth=args.birth_date or profile.get('birth_date')
        school=args.school_start or profile.get('school_start')
        result=inspect(args.date,state,args.number,fingerprint,
                       parse_date(birth) if birth else None,parse_date(school) if school else None,
                       profile,family.get('semesters') or [])
    except (ValueError,OSError,OverflowError,KeyError,TypeError) as exc: parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
