#!/usr/bin/env python3
"""Download FDA summary PDFs and extract text for analysis.

Finds summary PDF links on submission pages, downloads PDFs, and extracts
text into a local (gitignored) folder.
"""

import argparse
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PDF_RE = re.compile(r"\.pdf($|\?)", re.IGNORECASE)
SUMMARY_KEYWORDS = [
    "summary of safety and effectiveness",
    "summary of safety",
    "ssed",
    "summary",
    "510(k) summary",
    "executive summary",
    "decision summary",
]
NEGATIVE_KEYWORDS = [
    "label",
    "labeling",
    "instructions",
    "ifu",
    "manual",
    "brochure",
    "addendum",
    "review",
]


def download_url(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "fda-ai-ml-dashboard-bot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._current_href = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = None
        for key, value in attrs:
            if key.lower() == "href":
                href = value
                break
        self._current_href = href
        self._current_text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a":
            return
        if self._current_href is None:
            return
        text = "".join(self._current_text).strip()
        self.links.append((self._current_href, text))
        self._current_href = None
        self._current_text = []


def parse_links(html_text):
    parser = LinkCollector()
    parser.feed(html_text)
    return parser.links


def score_link(text, href):
    text_lower = (text or "").lower()
    href_lower = (href or "").lower()
    score = 0
    for keyword in SUMMARY_KEYWORDS:
        if keyword in text_lower:
            score += 3
        elif keyword in href_lower:
            score += 1
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in text_lower or keyword in href_lower:
            score -= 2
    return score


def find_summary_pdfs(html_text, base_url):
    links = parse_links(html_text)
    pdf_links = []
    for href, text in links:
        if not href:
            continue
        if not PDF_RE.search(href):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        pdf_links.append({"url": absolute, "text": text or ""})

    if not pdf_links:
        return []

    scored = []
    for link in pdf_links:
        score = score_link(link["text"], link["url"])
        scored.append({**link, "score": score})

    preferred = [item for item in scored if item["score"] > 0]
    candidates = preferred or scored
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def load_json(path):
    if not Path(path).exists():
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_records(input_json, index_html):
    data = load_json(input_json)
    if data is not None:
        return data

    content = Path(index_html).read_text(encoding="utf-8")
    match = re.search(r"const rawData = (\[.*?\]);", content, re.S)
    if not match:
        raise RuntimeError("rawData not found in index.html")
    return json.loads(match.group(1))


def load_cache(path):
    cache = load_json(path)
    return cache if isinstance(cache, dict) else {}


def save_cache(path, cache):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2, ensure_ascii=False)


def ensure_pdf(url, pdf_path, force=False):
    if pdf_path.exists() and not force:
        return
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    data = download_url(url)
    pdf_path.write_bytes(data)


def extract_with_pdftotext(pdf_path, text_path):
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return False
    result = subprocess.run(
        [pdftotext, "-layout", "-enc", "UTF-8", str(pdf_path), str(text_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pdftotext failed")
    return True


def extract_with_pypdf(pdf_path, text_path):
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return False

    reader = PdfReader(str(pdf_path))
    chunks = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        chunks.append(extracted)
    text = "\n\n".join(chunks).strip()
    text_path.write_text(text, encoding="utf-8")
    return True


def extract_text(pdf_path, text_path):
    if extract_with_pdftotext(pdf_path, text_path):
        return "pdftotext"
    if extract_with_pypdf(pdf_path, text_path):
        return "pypdf"
    raise RuntimeError("No PDF text extractor found. Install pdftotext or pypdf.")


def main():
    parser = argparse.ArgumentParser(
        description="Download FDA summary PDFs and extract text."
    )
    parser.add_argument("--input-json", default="data/ai-ml-enabled-devices-enriched.json")
    parser.add_argument("--index-html", default="index.html")
    parser.add_argument("--pdf-dir", default="data/summary-pdfs")
    parser.add_argument("--text-dir", default="data/summary-text")
    parser.add_argument("--cache", default="data/summary-cache.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--throttle", type=float, default=0.4)

    args = parser.parse_args()

    records = load_records(args.input_json, args.index_html)
    cache = load_cache(args.cache)

    processed = 0
    for record in records:
        submission_id = (record.get("submission_id") or "").strip()
        submission_url = (record.get("submission_url") or "").strip()
        if not submission_id or not submission_url:
            continue

        if args.limit and processed >= args.limit:
            break

        cache_entry = cache.get(submission_id, {})
        summary_links = cache_entry.get("summary_links")

        if not summary_links or args.force:
            try:
                html = download_url(submission_url).decode("utf-8", errors="ignore")
            except urllib.error.URLError:
                cache[submission_id] = {"summary_links": []}
                save_cache(args.cache, cache)
                continue

            candidates = find_summary_pdfs(html, submission_url)
            summary_links = [item["url"] for item in candidates]
            cache[submission_id] = {"summary_links": summary_links}
            save_cache(args.cache, cache)
            time.sleep(args.throttle)

        if not summary_links:
            continue

        to_download = summary_links if args.all else summary_links[:1]

        for index, pdf_url in enumerate(to_download, start=1):
            suffix = f"-{index}" if args.all else ""
            pdf_path = Path(args.pdf_dir) / f"{submission_id}{suffix}.pdf"
            text_path = Path(args.text_dir) / f"{submission_id}{suffix}.txt"

            if text_path.exists() and not args.force:
                continue

            try:
                ensure_pdf(pdf_url, pdf_path, force=args.force)
                method = extract_text(pdf_path, text_path)
                text_size = text_path.stat().st_size if text_path.exists() else 0
                print(f"{submission_id}: extracted via {method} ({text_size} bytes)")
            except Exception as exc:
                print(f"{submission_id}: failed ({exc})")

            time.sleep(args.throttle)

        processed += 1


if __name__ == "__main__":
    main()
