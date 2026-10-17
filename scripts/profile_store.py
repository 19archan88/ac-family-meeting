#!/usr/bin/env python3
"""Private family profile storage. Never infer consent or persist example data."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
import uuid
from family_context import parse_date, child_context

SKILL_ROOT = Path(__file__).resolve().parents[1]


def archive_path(value):
    path = Path(value).expanduser().resolve()
    if path == SKILL_ROOT or SKILL_ROOT in path.parents:
        raise ValueError('Private archive must be outside the skill directory')
    return path


def read_profile(archive):
    path = archive_path(archive) / 'FAMILY-profile.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Profile must be an object')
    return value


def merge(old, patch):
    """Merge objects; keyed member lists merge by id, other lists replace explicitly."""
    result = deepcopy(old)
    for key, value in patch.items():
        if key in ('children', 'family_members'):
            if not isinstance(value, list):
                raise ValueError(f'{key} must be a list')
            existing = {item['id']: deepcopy(item) for item in result.get(key, [])}
            seen = set()
            for item in value:
                if not isinstance(item, dict) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', str(item.get('id', ''))):
                    raise ValueError('Each member needs a stable safe id')
                if item['id'] in seen:
                    raise ValueError('Duplicate member id')
                seen.add(item['id'])
                existing[item['id']] = merge(existing.get(item['id'], {}), item)
            result[key] = list(existing.values())
        elif key == 'school_baselines':
            if not isinstance(value, list):
                raise ValueError('school_baselines must be a list')
            baselines = {item['effective_date']: deepcopy(item) for item in result.get(key, [])}
            seen = set()
            for item in value:
                effective = item['effective_date']
                parse_date(effective)
                if effective in seen:
                    raise ValueError('Duplicate school baseline date')
                seen.add(effective)
                baselines[effective] = deepcopy(item)
            result[key] = [baselines[k] for k in sorted(baselines)]
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def status(profile, child_id=None):
    if profile is None:
        return {'state': 'not_started', 'ready': False, 'missing': ['initialization']}
    children = profile.get('children', [])
    if not isinstance(children, list):
        raise ValueError('children must be a list')
    ids = set()
    for item in children:
        if not isinstance(item, dict) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', str(item.get('id', ''))):
            raise ValueError('Invalid child id')
        if item['id'] in ids:
            raise ValueError('Duplicate child id')
        ids.add(item['id'])
        birth = parse_date(item['birth_date']) if item.get('birth_date') else None
        school = parse_date(item['school_start']) if item.get('school_start') else None
        dates = [d for d in (birth, school) if d]
        if item.get('age_reference'):
            dates.append(parse_date(item['age_reference']['as_of']))
        child_context(max(dates) if dates else parse_date('2030-01-01'), birth, school, item)
        observation = item.get('school_observation')
        if observation:
            parse_date(observation['as_of'])
            if not observation.get('label'):
                raise ValueError('School observation needs a confirmed label')
    if child_id is None and len(children) == 1:
        child_id = children[0]['id']
    child = next((c for c in children if c.get('id') == child_id), None)
    missing = []
    if not profile.get('timezone'):
        missing.append('timezone')
    if child is None:
        missing.append('target_child')
    else:
        if not child.get('alias'):
            missing.append('alias')
        if not (child.get('birth_date') or child.get('age_reference')):
            missing.append('age')
        if not (child.get('school_observation') or child.get('school_baselines')):
            missing.append('school')
    if not profile.get('family_members'):
        missing.append('family_members')
    decisions = dict(profile.get('onboarding', {}).get('decisions', {}))
    # A sibling's decision must never satisfy this child's missing information.
    if len(children) > 1:
        for key in ('alias', 'age', 'school'):
            decisions.pop(key, None)
    if child:
        decisions.update(child.get('onboarding', {}).get('decisions', {}))
    if any(v not in ('deferred', 'declined') for v in decisions.values()):
        raise ValueError('Missing-field decisions must be deferred or declined')
    unanswered = [key for key in missing if decisions.get(key) not in ('deferred', 'declined')]
    acknowledged = profile.get('onboarding', {}).get('acknowledged') is True
    ready = acknowledged and child is not None and not unanswered
    return {'state': 'complete' if ready and not missing else 'partial',
            'ready': ready, 'child_id': child_id, 'missing': missing,
            'unanswered': unanswered, 'acknowledged': acknowledged}


def update_profile(archive, patch, confirmed=False):
    if not confirmed:
        raise ValueError('Only user-provided or confirmed information may be saved')
    if not isinstance(patch, dict):
        raise ValueError('Patch must be an object')
    root = archive_path(archive)
    old = read_profile(root) or {'profile_version': '2.0', 'family_id': str(uuid.uuid4()),
                                 'children': [], 'family_members': [], 'revision': 0}
    # Metadata is maintained here, never trusted from imported patches.
    forbidden = {'family_id', 'revision', 'last_updated', 'archive_path', 'profile_version', 'change_history'}
    if forbidden.intersection(patch):
        raise ValueError('Patch contains system-managed metadata')
    value = merge(old, patch)
    status(value)  # Validate before touching existing storage.
    value.update(profile_version='2.0', archive_path=str(root),
                 family_id=old.get('family_id') or str(uuid.uuid4()),
                 revision=old.get('revision', 0) + 1,
                 last_updated=datetime.now(timezone.utc).isoformat())
    value['change_history'] = old.get('change_history', []) + [{
        'revision': value['revision'], 'confirmed_at': value['last_updated'],
        'source': 'user_confirmed', 'patch': deepcopy(patch)}]
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'FAMILY-profile.json'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                         prefix='.profile-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        if json.loads(temporary.read_text(encoding='utf-8')) != value:
            raise OSError('Temporary profile verification failed')
        temporary.replace(path)
        if read_profile(root) != value:
            raise OSError('Saved profile verification failed')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return value


def require_ready(archive, child_id=None):
    value = read_profile(archive)
    result = status(value, child_id)
    if not result['ready']:
        raise ValueError('Initialization requires user response: ' + json.dumps(result, ensure_ascii=False))
    return value, result['child_id']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'update'])
    parser.add_argument('--archive', required=True)
    parser.add_argument('--child-id')
    parser.add_argument('--patch', help='Private JSON file containing only user-confirmed updates')
    parser.add_argument('--confirmed', action='store_true')
    args = parser.parse_args()
    if args.command == 'update':
        if not args.patch:
            parser.error('update requires --patch')
        value = update_profile(args.archive, json.loads(Path(args.patch).read_text(encoding='utf-8-sig')), args.confirmed)
    else:
        value = read_profile(args.archive)
    print(json.dumps(status(value, args.child_id), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
