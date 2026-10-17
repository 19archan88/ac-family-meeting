"""Private render receipts preserve explicit display choices across safe retries."""
import base64
import hashlib
import json
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint():
    files = [Path(__file__), ROOT/'scripts/build_report_html.py', ROOT/'LICENSE', ROOT/'THIRD_PARTY_NOTICES.md']
    files += sorted(p for p in (ROOT/'assets/web').rglob('*') if p.is_file())
    return sha(json.dumps([(p.relative_to(ROOT).as_posix(), sha(p.read_bytes())) for p in files]).encode())


def write_receipt(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as handle:
            temp = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def settings_for(page, raw, report_id):
    match = re.search(r'<script id="report-settings" type="application/json">(.*?)</script>', page, re.S)
    if not match:
        raise ValueError('现有 HTML 缺少报告设置，无法安全恢复显示参数。')
    settings = json.loads(match[1])
    if not isinstance(settings, dict):
        raise ValueError('现有 HTML 的报告设置格式无效。')
    if (settings.get('reportId') != report_id or settings.get('sourceSha256') != sha(raw)
            or base64.b64decode(settings.get('markdownBase64', ''), validate=True) != raw):
        return None
    return settings


def render(builder, source, output=None, headline=None, audience=None, allowed=('parent', 'child')):
    source = Path(source).resolve()
    output = Path(output).resolve() if output else source.with_suffix('.html')
    if source.suffix.lower() != '.md' or output.suffix.lower() != '.html' or source == output:
        raise ValueError('须提供 Markdown 源文件和不同的 HTML 输出文件。')
    raw = source.read_bytes()
    if not raw.decode('utf-8-sig').strip():
        raise ValueError('报告正文为空。')
    receipt_path = output.parent/'.qa'/(output.name+'.render.json')
    saved = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
    if not isinstance(saved, dict):
        raise ValueError('渲染回执格式无效；请核对回执，不能直接覆盖。')
    identity = {'source': str(source), 'output': str(output), 'source_sha256': sha(raw)}
    same_source = all(saved.get(k) == v for k, v in identity.items())
    previous = saved.get('options') if same_source else None
    if previous is None and output.exists():
        existing = settings_for(output.read_text(encoding='utf-8'), raw, source.stem)
        if existing is not None:
            previous = {'headline': existing.get('headline'), 'audience': existing.get('audience')}
    if previous is not None and not isinstance(previous, dict):
        raise ValueError('渲染回执的显示参数无效。')
    previous = previous or {}
    options = {'headline': headline if headline is not None else previous.get('headline'),
               'audience': audience if audience is not None else previous.get('audience', 'parent')}
    if options['audience'] not in allowed or (options['headline'] is not None and not isinstance(options['headline'], str)):
        raise ValueError('显示参数无效，请明确指定 --headline / --audience。')
    # Do not associate old HTML hashes with new options after a failed rebuild.
    pending = dict(identity, options=options, status='rendering')
    write_receipt(receipt_path, pending)
    try:
        renderer = fingerprint()
        reuse = (same_source and saved.get('options') == options and saved.get('renderer_sha256') == renderer
                 and output.is_file() and saved.get('html_sha256') == sha(output.read_bytes()))
        if not reuse:
            builder(source, output, **options)
        settings = settings_for(output.read_text(encoding='utf-8'), raw, source.stem)
        if settings is None or settings.get('audience') != options['audience']:
            raise ValueError('生成的 HTML 与正文或阅读对象不一致。')
        if options['headline'] and settings.get('headline') != options['headline']:
            raise ValueError('生成的 HTML 提要与指定值不一致。')
    except Exception as exc:
        write_receipt(receipt_path, dict(pending, status='failed', error=str(exc)))
        raise
    write_receipt(receipt_path, dict(pending, status='complete', renderer_sha256=renderer,
                                   html_sha256=sha(output.read_bytes()), html_reused=reuse))
    return output
