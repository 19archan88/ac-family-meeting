"""Finish a reader-first report: build, verify and atomically apply a state delta.

Only sanitized report/delta inputs are accepted; content analysis stays with the agent.
Uses the Python standard library. See references/delivery-workflow.md for the contract.
"""
import argparse
import base64
import copy
from datetime import datetime, date, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import time

from build_report_html import build, ROOT
from meeting_context import inspect
from profile_store import read_profile, require_ready
from check_report_content import check_report
from render_retry import settings_for

COLLECTIONS = ('meetings', 'reports', 'actions', 'signals')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as f:
        temp = Path(f.name)
        f.write(raw)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def mark(receipt_path, stage, source=None):
    path = Path(receipt_path)
    if stage == 'start':
        if path.exists():
            raise ValueError('Use a new receipt for a new run; do not reset timing.')
        receipt = {'started_at': now(), 'status': 'analyzing'}
    else:
        receipt = read_json(path)
        if receipt['status'] != 'analyzing':
            raise ValueError('Only mark ready once, after content review.')
        source = Path(source).resolve()
        raw = source.read_bytes()
        if not raw.decode('utf-8-sig').strip():
            raise ValueError('Report is empty.')
        receipt.update(body_ready_at=now(), source=str(source), markdown_sha256=digest(raw), status='body_ready')
        receipt['analysis_wall_seconds'] = round((datetime.fromisoformat(receipt['body_ready_at']) - datetime.fromisoformat(receipt['started_at'])).total_seconds(), 3)
    atomic_json(path, receipt)
    return receipt


class PageCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag in ('script', 'img', 'iframe', 'source', 'video', 'audio') and attrs.get('src'):
            self.assets.append(attrs['src'])
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.assets.append(attrs.get('href', ''))


def verify(source, html):
    raw = Path(source).read_bytes()
    page = Path(html).read_text(encoding='utf-8')
    match = re.search(r'<script id="report-settings" type="application/json">(.*?)</script>', page, re.S)
    if not match:
        raise ValueError('Missing report settings.')
    settings = json.loads(match.group(1))
    if base64.b64decode(settings['markdownBase64'], validate=True) != raw or settings['sourceSha256'] != digest(raw):
        raise ValueError('Embedded Markdown differs from source.')
    if settings['reportId'] != Path(source).stem or '@@' in page:
        raise ValueError('Incorrect report ID or unresolved template marker.')
    check = PageCheck()
    check.feed(page)
    if len(check.ids) != len(set(check.ids)):
        raise ValueError('Duplicate HTML element IDs.')
    if not {'report-settings', 'save-png', 'save-markdown'} <= set(check.ids):
        raise ValueError('Missing report controls.')
    if any(not value.startswith('data:') for value in check.assets):
        raise ValueError('Non-embedded resource found.')
    return {'embedded_markdown': 'exact', 'sha256': digest(raw), 'resources': 'self_contained'}


def validate_ids(state):
    for collection in COLLECTIONS:
        rows = state.get(collection)
        if not isinstance(rows, list):
            raise ValueError('Missing collection: ' + collection)
        ids = [x.get('id') for x in rows]
        if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
            raise ValueError('Missing or duplicate IDs in ' + collection)
    for meeting in state['meetings']:
        date.fromisoformat(meeting['date'])
    meetings = {m['id'] for m in state['meetings']}
    weekly = [r.get('meeting_id') for r in state['reports'] if r.get('type') == 'weekly_combined']
    if len(weekly) != len(set(weekly)) or any(x not in meetings for x in weekly):
        raise ValueError('Weekly report must reference one unique existing meeting.')


def latest_date(row, state):
    meetings = {m['id']: m['date'] for m in state['meetings']}
    dates = []
    for value in [row] + row.get('updates', []) + row.get('reviews', []):
        if value.get('meeting_date'):
            dates.append(value['meeting_date'])
        if value.get('current_as_of'):
            dates.append(value['current_as_of'])
        for key in ('meeting_id', 'latest_review_meeting_id'):
            if value.get(key) in meetings:
                dates.append(meetings[value[key]])
    return max(dates, default='0001-01-01')


def merge_delta(before, delta):
    """Add records; append history; allow current-field changes only at a valid as-of date."""
    if set(delta) - {'base_sha256', 'add', 'update', 'set', 'append_reminders', 'history_confirmation'}:
        raise ValueError('Unknown delta field.')
    state = copy.deepcopy(before)
    validate_ids(state)
    for collection, records in delta.get('add', {}).items():
        if collection not in COLLECTIONS:
            raise ValueError('Unsupported collection: ' + collection)
        for record in records:
            if record.get('id') in {x['id'] for x in state[collection]}:
                raise ValueError('Duplicate record; use update or retry the same patch.')
            if collection == 'meetings':
                result = inspect(record['date'], state, record.get('number'), record.get('source_sha256'))
                if result['requires_review'] and not delta.get('history_confirmation', '').strip():
                    raise ValueError('Meeting history anomaly needs recorded user confirmation: ' + '; '.join(result['warnings']))
                if record.get('source_sha256') and any(m.get('source_sha256') == record['source_sha256'] for m in state['meetings']):
                    raise ValueError('Duplicate source: revise its existing meeting, do not add one.')
            state[collection].append(copy.deepcopy(record))
    for change in delta.get('update', []):
        if set(change) - {'collection', 'id', 'set', 'append', 'as_of'}:
            raise ValueError('Unknown update field.')
        collection = change['collection']
        if collection not in COLLECTIONS:
            raise ValueError('Unsupported update collection.')
        found = [x for x in state[collection] if x['id'] == change['id']]
        if not found:
            raise ValueError('Cannot update missing record: ' + change['id'])
        row = found[0]
        fields = change.get('set', {})
        if 'id' in fields or 'id' in change.get('append', {}):
            raise ValueError('Stable ID cannot change.')
        if any(isinstance(row.get(key), list) for key in fields):
            raise ValueError('Existing lists are append-only; preserve history.')
        if fields and collection in ('actions', 'signals'):
            as_of = change.get('as_of', '')
            if date.fromisoformat(as_of).isoformat() != as_of:
                raise ValueError('as_of must use YYYY-MM-DD.')
            if as_of < latest_date(row, state):
                raise ValueError('Backfill may append history but cannot replace newer current fields.')
            if 'current_as_of' in fields and fields['current_as_of'] != as_of:
                raise ValueError('Current evidence date must equal as_of.')
            row['current_as_of'] = as_of
        if collection == 'meetings' and any(key in fields and fields[key] != row.get(key) for key in ('date', 'number', 'source_sha256')):
            if not delta.get('history_confirmation', '').strip():
                raise ValueError('Changing meeting identity needs recorded user confirmation.')
        if collection == 'reports' and fields and fields.get('version', row.get('version', 0)) <= row.get('version', 0):
            raise ValueError('Report replacement needs an increased version; context notes can be appended.')
        row.update(copy.deepcopy(fields))
        for key, events in change.get('append', {}).items():
            if not isinstance(events, list) or not isinstance(row.get(key, []), list):
                raise ValueError('append requires lists.')
            for event in events:
                if event not in row.setdefault(key, []):
                    row[key].append(copy.deepcopy(event))
    metadata = delta.get('set', {})
    if set(metadata) - {'updated_at', 'history_coverage_note'}:
        raise ValueError('Only updated_at and history_coverage_note can be set at root.')
    state.update(copy.deepcopy(metadata))
    for reminder in delta.get('append_reminders', []):
        if reminder not in state.setdefault('reminders', []):
            state['reminders'].append(copy.deepcopy(reminder))
    state['meetings'].sort(key=lambda x: (x['date'], x['id']))
    validate_ids(state)
    return state


def commit(state_path, patch_path, source, html, backup_dir, verified_hash):
    state_path, patch_path = Path(state_path), Path(patch_path)
    delta = read_json(patch_path)
    patch_hash = digest(patch_path.read_bytes())
    report_hash = digest(Path(source).read_bytes())
    if report_hash != verified_hash:
        raise ValueError('Source changed after HTML verification.')
    lock = state_path.with_suffix(state_path.suffix + '.delivery-lock')
    # Cooperative writers are serialized; compare original bytes before replacing too.
    with lock.open('x', encoding='utf-8'):
        pass
    try:
        raw = state_path.read_bytes()
        before = json.loads(raw.decode('utf-8-sig'))
        previous = before.get('delivery_commits', {}).get(patch_hash)
        if previous:
            if previous['markdown_sha256'] != report_hash or previous['report_id'] != Path(source).stem:
                raise ValueError('A committed patch cannot be reused for changed report content.')
            return 'already_committed'
        if delta.get('base_sha256') != digest(raw):
            raise ValueError('State changed since reading: reload and rebase the delta.')
        state = merge_delta(before, delta)
        reports = [r for r in state['reports'] if r['id'] == Path(source).stem]
        if len(reports) != 1:
            raise ValueError('State must include this report ID.')
        expected_paths = {Path(source).resolve(), Path(html).resolve()}
        actual_paths = {(state_path.parent.parent / x).resolve() for x in reports[0].get('artifacts', [])}
        if not expected_paths <= actual_paths:
            raise ValueError('Report artifacts must include the verified MD and HTML paths.')
        state.setdefault('delivery_commits', {})[patch_hash] = {'report_id': Path(source).stem, 'markdown_sha256': report_hash, 'committed_at': now()}
        backup = Path(backup_dir) / ('STATE-' + digest(raw) + '.json')
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(raw)
        if backup.read_bytes() != raw or state_path.read_bytes() != raw:
            raise ValueError('Backup mismatch or state modified by another writer.')
        atomic_json(state_path, state)
        return 'committed'
    finally:
        lock.unlink(missing_ok=True)


def renderer_digest():
    files = [ROOT / 'scripts/build_report_html.py', ROOT / 'LICENSE', ROOT / 'THIRD_PARTY_NOTICES.md']
    files += sorted(p for p in (ROOT / 'assets/web').rglob('*') if p.is_file())
    return digest(json.dumps([(str(p.relative_to(ROOT)), digest(p.read_bytes())) for p in files]).encode())


def finish(source, receipt_path, state_path=None, patch_path=None, no_archive=False, headline=None, audience=None, family_archive=None, onboarding_acknowledged=False):
    source, receipt_path = Path(source).resolve(), Path(receipt_path)
    if family_archive:
        family = read_profile(family_archive)
        if not family or not family.get('children'):
            raise ValueError('Complete family onboarding before delivery')
        for child in family['children']:
            require_ready(family_archive, child['id'])
        root = Path(family_archive).resolve()
        if root not in source.parents or (state_path and root not in Path(state_path).resolve().parents):
            raise ValueError('Report and state must belong to the selected family archive')
    elif not (no_archive and onboarding_acknowledged):
        raise ValueError('Provide --family-archive or explicitly acknowledge temporary onboarding with --no-archive')
    if bool(state_path and patch_path) == bool(no_archive) or bool(state_path) != bool(patch_path):
        raise ValueError('Provide both state and patch, or explicitly choose no_archive.')
    receipt = read_json(receipt_path)
    if receipt.get('status') not in ('body_ready', 'failed', 'complete'):
        raise ValueError('Mark reviewed body ready before finishing.')
    if receipt.get('source') != str(source) or receipt.get('markdown_sha256') != digest(source.read_bytes()):
        raise ValueError('Body changed after ready; review and start a new delivery receipt.')
    tick = time.perf_counter()
    try:
        html = source.with_suffix('.html')
        previous = receipt.get('render_options')
        if previous is None and receipt['status'] == 'body_ready' and html.exists() and (headline is None or audience is None):
            settings = settings_for(html.read_text(encoding='utf-8'), source.read_bytes(), source.stem)
            if settings is not None:
                verify(source, html)
                previous = {'headline': settings.get('headline'), 'audience': settings.get('audience', 'parent')}
        if previous is None and receipt['status'] in ('complete', 'failed') and html.exists():
            # Older receipts did not retain presentation arguments. Recover only
            # from a self-contained page whose embedded source is exactly this MD.
            verify(source, html)
            page = html.read_text(encoding='utf-8')
            settings = json.loads(re.search(r'<script id="report-settings" type="application/json">(.*?)</script>', page, re.S)[1])
            previous = {'headline': settings.get('headline'), 'audience': settings.get('audience', 'parent')}
        elif previous is None and receipt['status'] in ('complete', 'failed') and (headline is None or audience is None):
            raise ValueError('旧回执缺少显示参数且 HTML 不存在；请明确提供 --headline 和 --audience 后重试。')
        previous = previous or {}
        options = {'headline': headline if headline is not None else previous.get('headline'),
                   'audience': audience if audience is not None else previous.get('audience', 'parent')}
        if options['audience'] not in ('parent', 'family', 'guide'):
            raise ValueError('Invalid saved audience; provide an explicit --audience.')
        content_checks = check_report(source, options['audience'])
        cached = dict(receipt)
        # Persist choices before rendering so even a failed first build can retry.
        receipt['render_options'] = options
        # Preserve parameters even if reading template resources fails, and never
        # associate old artifact hashes with newly requested options on failure.
        receipt.pop('html_sha256', None)
        receipt.pop('renderer_sha256', None)
        atomic_json(receipt_path, receipt)
        renderer_sha = renderer_digest()
        reuse = (cached.get('render_options') == options and cached.get('renderer_sha256') == renderer_sha
                 and html.is_file() and cached.get('html_sha256') == digest(html.read_bytes()))
        if not reuse:
            html = build(source, **options)
        checks = verify(source, html)
        checks['content_contract'] = content_checks
        receipt.update(renderer_sha256=renderer_sha, html_sha256=digest(html.read_bytes()),
                       html=str(html), html_reused=reuse)
        receipt['build_verify_seconds'] = round(time.perf_counter() - tick, 3)
        receipt['files_checked_at'] = now()
        atomic_json(receipt_path, receipt)
        tick = time.perf_counter()
        result = 'not_requested' if no_archive else commit(state_path, patch_path, source, html, receipt_path.parent / 'backups', checks['sha256'])
        receipt.update(status='complete', archive_result=result, archive_seconds=round(time.perf_counter() - tick, 3), finished_at=now(), checks=checks, html=str(html))
        receipt.pop('error', None)
    except Exception as exc:
        receipt.update(status='failed', error=str(exc))
        atomic_json(receipt_path, receipt)
        raise
    atomic_json(receipt_path, receipt)
    return {k: receipt[k] for k in ('status', 'source', 'html', 'analysis_wall_seconds', 'build_verify_seconds', 'archive_seconds', 'archive_result')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start')
    start.add_argument('--receipt', required=True)
    ready = sub.add_parser('ready')
    ready.add_argument('source')
    ready.add_argument('--receipt', required=True)
    end = sub.add_parser('finish')
    end.add_argument('source')
    end.add_argument('--receipt', required=True)
    end.add_argument('--state')
    end.add_argument('--patch')
    end.add_argument('--no-archive', action='store_true')
    end.add_argument('--family-archive')
    end.add_argument('--onboarding-acknowledged', action='store_true')
    end.add_argument('--headline')
    end.add_argument('--audience', choices=('parent', 'family', 'guide'), default=None,
                     help='First run defaults to parent; retries retain the saved audience when omitted.')
    args = parser.parse_args()
    if args.command == 'finish':
        result = finish(args.source, args.receipt, args.state, args.patch, args.no_archive, args.headline, args.audience, args.family_archive, args.onboarding_acknowledged)
    else:
        result = mark(args.receipt, args.command, getattr(args, 'source', None))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    from cli_support import run_cli
    run_cli(main)
