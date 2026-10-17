#!/usr/bin/env python3
"""Build a portable, offline HTML companion without modifying the source report/state."""

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def build(source, output=None, headline=None, audience="parent"):
    source = Path(source).resolve()
    if source.suffix.lower() != ".md":
        raise ValueError("The source must be a Markdown report.")
    raw = source.read_bytes()
    markdown = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not markdown.strip():
        raise ValueError("The report is empty.")
    title_match = re.search(r"^#\s+(.+)$", markdown, re.M)
    title = title_match.group(1) if title_match else source.stem
    report_id = source.stem
    # A provisional report id may contain both a year and a later full meeting
    # date (for example FM-2026-PENDING-2026-09-18). Prefer the most specific
    # date so the cover never falls back to the earlier year-only fragment.
    period_matches = re.findall(r"\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4}", report_id)
    period = max(period_matches, key=lambda value: (len(value), period_matches.index(value))) if period_matches else None
    date_label = period.replace("-", " . ") if period else "家庭会议 · 长期珍藏"
    kind = ("历史会议纪要" if report_id.endswith("-minutes") else "历史双镜头分析" if report_id.endswith("-analysis")
            else "月度回望" if report_id.startswith("FM-M-") else "学期成长" if report_id.startswith("FM-S-")
            else "年度珍藏" if report_id.startswith("FM-Y-") else "会议纪要与双镜头分析"
            if report_id.startswith("FM-") else "使用与规范")
    version_match = re.search(r"prompt_version:\s*(v[\d.]+)", markdown)
    version = version_match.group(1) if version_match else "未标注"
    # Report kind comes from its stable id; do not infer the period from prose.
    lead_label = ("阅读提要" if audience == "guide" else
                  "本月的注脚" if report_id.startswith("FM-M-") else
                  "本学期的注脚" if report_id.startswith("FM-S-") else
                  "这一年的注脚" if report_id.startswith("FM-Y-") else
                  "本周的注脚" if report_id.startswith("FM-") else "阅读提要")
    settings = {
        "title": title, "headline": headline or title, "reportId": report_id,
        "dateLabel": date_label, "kind": kind, "version": version,
        "audience": audience, "sourceName": source.name, "leadLabel": lead_label,
        "sourceSha256": hashlib.sha256(raw).hexdigest(),
        "markdownBase64": base64.b64encode(raw).decode("ascii"),
        "renderVersion": "2.1.2",
    }
    web = ROOT / "assets" / "web"
    template = (web / "report.html").read_text(encoding="utf-8")
    # Base64 isolates private source text from HTML/JS parsing; no remote fonts or assets.
    replacements = {
        "@@TITLE@@": html.escape(title),
        "@@FALLBACK@@": html.escape(markdown),
        "@@SETTINGS@@": json.dumps(settings, ensure_ascii=True).replace("<", "\\u003c"),
        "@@CSS@@": (web / "report.css").read_text(encoding="utf-8"),
        "@@ART@@": base64.b64encode((web / "cover-art.svg").read_bytes()).decode("ascii"),
        "@@MARKED@@": (web / "vendor" / "marked.umd.js").read_text(encoding="utf-8"),
        "@@CANVAS@@": (web / "vendor" / "html2canvas.min.js").read_text(encoding="utf-8"),
        "@@PNG@@": (web / "png-encoder.js").read_text(encoding="utf-8"),
        "@@JS@@": (web / "report.js").read_text(encoding="utf-8"),
    }

    # Keep full license notices with redistributed inline code without adding visible UI.
    notices = {name: (ROOT / name).read_text(encoding="utf-8") for name in (
        "LICENSE", "THIRD_PARTY_NOTICES.md", "assets/web/vendor/marked-LICENSE.md",
        "assets/web/vendor/html2canvas-LICENSE.txt")}
    license_data = json.dumps(notices, ensure_ascii=True).replace("<", "\\u003c")
    replacements["@@LICENSES@@"] = license_data
    result = re.sub(r"@@[A-Z]+@@", lambda m: replacements[m.group(0)], template)
    output = Path(output).resolve() if output else source.with_suffix(".html")
    if output.suffix.lower() != ".html" or output == source:
        raise ValueError("Output must be an HTML file distinct from the source.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".html.tmp")
    # Keep embedded text stable on Windows; the Base64 source retains original bytes.
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(result)
    temporary.replace(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="The complete, anonymized Markdown report")
    parser.add_argument("--output")
    parser.add_argument("--headline", help="Optional editorial title; must not introduce unsupported claims")
    parser.add_argument("--audience", choices=("parent", "family", "guide"), default="parent")
    args = parser.parse_args()
    print(build(args.source, args.output, args.headline, args.audience))


if __name__ == "__main__":
    main()
