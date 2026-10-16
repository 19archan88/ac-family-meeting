"""Private family profile calculations; no meeting/report scheduling rules."""
import calendar, re
from datetime import date

def parse_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Date must use YYYY-MM-DD")
    return date.fromisoformat(value)


def add_months(start, months):
    total = start.year * 12 + start.month - 1 + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def elapsed(start, end):
    if end < start:
        raise ValueError("End date precedes start date")
    months = (end.year - start.year) * 12 + end.month - start.month
    if add_months(start, months) > end:
        months -= 1
    anniversary = add_months(start, months)
    return {"years": months // 12, "months": months % 12,
            "total_months": months, "days": (end - anniversary).days,
            "total_days": (end - start).days}


def grade_context(day, baselines):
    """Use the latest confirmed baseline, preserving earlier school history."""
    if not baselines:
        return None
    applicable = []
    seen = set()
    for baseline in baselines:
        effective = parse_date(baseline['effective_date'])
        if effective in seen:
            raise ValueError('Duplicate school baseline date')
        seen.add(effective)
        index = baseline['grade_index']
        if type(index) is not int or index < 1:
            raise ValueError('grade_index must be a positive integer')
        promotion = baseline['promotion_day']
        if not re.fullmatch(r'\d{2}-\d{2}', promotion):
            raise ValueError('promotion_day must use MM-DD')
        boundary = parse_date('2001-' + promotion)  # Must exist every year.
        stages = baseline['stages']
        if not stages or any(not s['name'] or type(s['years']) is not int or s['years'] < 1 for s in stages):
            raise ValueError('Each school stage needs a name and positive years')
        if index > sum(s['years'] for s in stages):
            raise ValueError('Baseline grade exceeds configured school stages')
        if effective <= day:
            applicable.append((effective, baseline, boundary))
    if not applicable:
        return None
    effective, baseline, boundary = max(applicable, key=lambda item: item[0])
    mmdd = (boundary.month, boundary.day)
    academic = lambda d: d.year - ((d.month, d.day) < mmdd)
    index = baseline['grade_index'] + academic(day) - academic(effective)
    remaining = index
    label = None
    for stage in baseline['stages']:
        if remaining <= stage['years']:
            label = f"{stage['name']}{remaining}年级"
            break
        remaining -= stage['years']
    return {'grade': label, 'school_year_index': index,
            'baseline_date': effective.isoformat(),
            'status': 'projected' if label else 'beyond_configured_stages',
            'notice': '依据家长确认的学籍基准和升年级规则推算；实际学籍变动以家长校正为准。'}


def child_context(day, birth=None, school_start=None, profile=None):
    profile = profile or {}
    if birth is not None and school_start is not None and school_start < birth:
        raise ValueError("School start precedes birth")
    age = elapsed(birth, day) if birth is not None else None
    age_label = f"{age['years']}岁{age['months']}个月" if age is not None else None
    age_precision = 'birth_date' if age is not None else None
    reference = profile.get('age_reference')
    if age is None and reference:
        reference_day = parse_date(reference['as_of'])
        years, months = reference['years'], reference['months']
        if type(years) is not int or years < 0 or type(months) is not int or not 0 <= months < 12:
            raise ValueError('Age reference needs nonnegative years and months in 0..11')
        if day >= reference_day:
            total = years * 12 + months + elapsed(reference_day, day)['total_months']
            age = {'years': total // 12, 'months': total % 12, 'total_months': total}
            age_label = f"约{age['years']}岁{age['months']}个月"
            age_precision = 'approximate_reference'
    school = None
    if school_start is not None:
        if day < school_start:
            school = {"enrolled": False, "grade": None,
                      "days_until_start": (school_start - day).days}
        else:
            school = {"enrolled": True, "grade": None,
                      "elapsed": elapsed(school_start, day),
                      "elapsed_day_convention": "入学当日已过0天；不含起始日"}
    grade = grade_context(day, profile.get('school_baselines'))
    if grade is not None:
        if school_start is not None and day < school_start:
            raise ValueError('School baseline conflicts with school entry date')
        school = school or {'enrolled': True, 'elapsed': None}
        school.update(grade)
    return {"birth_date": birth.isoformat() if birth is not None else None,
            "age": age,
            "age_label": age_label, "age_precision": age_precision,
            "school_start": school_start.isoformat() if school_start is not None else None,
            "school": school}
