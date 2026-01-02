#!/usr/bin/env python3
"""Update FDA AI/ML device data and refresh the dashboard embed.

Downloads the source XML, parses it into structured rows, enriches entries
with openFDA submission dates, writes an enriched JSON file, and replaces the
embedded rawData block in index.html.
"""

import argparse
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCE_URL_DEFAULT = "https://www.fda.gov/media/178565/download?attachment"

CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
REPLACEMENTS = {
    "\u0091": "'",
    "\u0092": "'",
    "\u0093": '"',
    "\u0094": '"',
    "\u0096": "-",
    "\u0097": "-",
    "\u0099": "TM",
}

SUBMISSION_ID_RE = re.compile(r"(DEN\d+|K\d+|P\d+)", re.IGNORECASE)


def clean_text(value):
    if value is None:
        return ""
    text = str(value)
    for src, dst in REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = CONTROL_RE.sub("", text)
    return text.strip()


def normalize_date(value):
    if not value:
        return ""
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", raw):
        return raw.replace("/", "-")
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", raw):
        month, day, year = raw.split("/")
        return f"{year}-{month}-{day}"
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return ""


def days_between(start_iso, end_iso):
    if not start_iso or not end_iso:
        return None
    try:
        start = dt.date.fromisoformat(start_iso)
        end = dt.date.fromisoformat(end_iso)
    except ValueError:
        return None
    if end < start:
        return None
    return (end - start).days


def build_submission_url(submission_id):
    if not submission_id:
        return ""
    submission_id = submission_id.upper()
    if submission_id.startswith("K"):
        return (
            "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/"
            f"cfPMN/pmn.cfm?ID={submission_id}"
        )
    if submission_id.startswith("P"):
        return (
            "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/"
            f"cfpma/pma.cfm?id={submission_id}"
        )
    if submission_id.startswith("DEN"):
        return (
            "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/"
            f"cfpmn/denovo.cfm?id={submission_id}"
        )
    return ""


def parse_submission(raw_value):
    raw_value = raw_value or ""
    raw_value = raw_value.strip()

    hyperlink_match = re.search(
        r'HYPERLINK\("([^"]+)",\s*"([^"]+)"\)', raw_value, re.IGNORECASE
    )
    url = ""
    submission_id = ""
    if hyperlink_match:
        url = hyperlink_match.group(1).strip()
        submission_id = hyperlink_match.group(2).strip().upper()
    else:
        url_match = re.search(r"https?://[^\s\)\"]+", raw_value)
        if url_match:
            url = url_match.group(0)
        id_match = SUBMISSION_ID_RE.search(raw_value)
        if not id_match and url:
            id_match = SUBMISSION_ID_RE.search(url)
        if id_match:
            submission_id = id_match.group(1).upper()

    if not submission_id and url:
        id_match = SUBMISSION_ID_RE.search(url)
        if id_match:
            submission_id = id_match.group(1).upper()

    if not url and submission_id:
        url = build_submission_url(submission_id)

    return submission_id, url


def download_url(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "fda-ai-ml-dashboard-bot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_openfda(submission_id, cache, throttle=0.1, retries=3):
    if not submission_id:
        return {"received_date": "", "decision_date_openfda": ""}

    submission_id = submission_id.upper()
    cached = cache.get(submission_id)
    if cached:
        return cached

    if submission_id.startswith("K"):
        endpoint = "https://api.fda.gov/device/510k.json"
        query_field = "k_number"
    elif submission_id.startswith("P"):
        endpoint = "https://api.fda.gov/device/pma.json"
        query_field = "pma_number"
    else:
        return {"received_date": "", "decision_date_openfda": ""}

    url = f"{endpoint}?search={query_field}:{submission_id}&limit=1"

    for attempt in range(retries):
        try:
            payload = download_url(url)
            data = json.loads(payload.decode("utf-8"))
            results = data.get("results") or []
            if not results:
                cache[submission_id] = {
                    "received_date": "",
                    "decision_date_openfda": "",
                    "source": query_field,
                }
                return cache[submission_id]
            record = results[0]
            received_raw = (
                record.get("received_date")
                or record.get("date_received")
                or record.get("receive_date")
                or ""
            )
            decision_raw = record.get("decision_date") or ""
            received_date = normalize_date(received_raw)
            decision_date = normalize_date(decision_raw)
            cache[submission_id] = {
                "received_date": received_date,
                "decision_date_openfda": decision_date,
                "source": query_field,
            }
            time.sleep(throttle)
            return cache[submission_id]
        except (urllib.error.URLError, json.JSONDecodeError):
            if attempt == retries - 1:
                break
            time.sleep(throttle * (attempt + 1))

    return {"received_date": "", "decision_date_openfda": ""}


def parse_xml_rows(xml_bytes):
    root = ET.fromstring(xml_bytes)
    rows = []
    for row in root.findall("./row"):
        decision_date = clean_text(row.findtext("Date_of_final_decision", ""))
        submission_raw = row.findtext("Submission_number", "")
        submission_id, submission_url = parse_submission(submission_raw)
        device = clean_text(row.findtext("Device", ""))
        company = clean_text(row.findtext("Company", ""))
        panel = clean_text(row.findtext("Panel", ""))
        code = clean_text(row.findtext("Primary_product_code", ""))

        year = None
        if decision_date:
            parts = decision_date.split("/")
            if len(parts) == 3 and parts[2].isdigit():
                year = int(parts[2])

        rows.append(
            {
                "date": decision_date,
                "year": year or 0,
                "device": device,
                "company": company,
                "panel": panel,
                "code": code,
                "submission_id": submission_id,
                "submission_url": submission_url,
                "summary_url": "",
                "received_date": "",
                "decision_date_openfda": "",
                "days_to_decision": None,
            }
        )
    return rows


def update_index_html(index_path, data):
    path = Path(index_path)
    content = path.read_text(encoding="utf-8")
    data_json = json.dumps(data, ensure_ascii=False)
    new_content, count = re.subn(
        r"const rawData = \[.*?\];",
        f"const rawData = {data_json};",
        content,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Unable to locate rawData block in index.html")
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")


def write_enriched_json(output_path, data):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Update FDA AI/ML device data.")
    parser.add_argument("--source-url", default=SOURCE_URL_DEFAULT)
    parser.add_argument("--source-xml", default="ai-ml-enabled-devices-xml.xml")
    parser.add_argument("--output-json", default="data/ai-ml-enabled-devices-enriched.json")
    parser.add_argument("--index-html", default="index.html")
    parser.add_argument("--skip-openfda", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--throttle", type=float, default=0.1)

    args = parser.parse_args()

    source_path = Path(args.source_xml)

    if args.skip_download:
        xml_bytes = source_path.read_bytes()
    else:
        xml_bytes = download_url(args.source_url)
        if not source_path.exists() or source_path.read_bytes() != xml_bytes:
            source_path.write_bytes(xml_bytes)

    rows = parse_xml_rows(xml_bytes)

    cache = {} if not args.skip_openfda else {}
    if not args.skip_openfda:
        for record in rows:
            submission_id = record.get("submission_id", "")
            openfda = fetch_openfda(submission_id, cache, throttle=args.throttle)
            record["received_date"] = openfda.get("received_date", "")
            record["decision_date_openfda"] = openfda.get("decision_date_openfda", "")
            record["days_to_decision"] = days_between(
                record["received_date"], record["decision_date_openfda"]
            )

    write_enriched_json(args.output_json, rows)
    update_index_html(args.index_html, rows)


if __name__ == "__main__":
    main()
