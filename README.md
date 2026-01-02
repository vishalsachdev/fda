# FDA AI/ML-Enabled Medical Devices

Interactive, single-page dashboard for exploring FDA-posted AI/ML-enabled medical device approvals since 2016. The site is designed to support a regulatory-facing narrative on growth, diversification, and new entrants.

Live site: https://vishalsachdev.github.io/fda/

## What this project shows
- Approvals per year, filtered by panel and search.
- Panel mix for the current filter set.
- New entrants per year (first appearance of companies and product codes).
- Time from submission to decision (median days with IQR) for 510(k) and PMA entries.
- A filterable device list with passthrough links to FDA submission records.

## Data source
- FDA AI/ML-Enabled Medical Devices list:
  https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-enabled-medical-devices
- Direct XML download used by the updater:
  https://www.fda.gov/media/178565/download?attachment
- The downloaded XML is stored as `ai-ml-enabled-devices-xml.xml`.
- The dashboard embeds the parsed data directly into `index.html` as JSON.
- The enriched dataset is stored as `data/ai-ml-enabled-devices-enriched.json`.
- Submission timing is enriched using openFDA 510(k) and PMA endpoints (date received and decision date).

## How to use locally
No build step required.
1. Open `index.html` in a browser.
2. Use the year range, panel filter, and search box to update charts and the device list.

## Methodology and assumptions
- Each row reflects a single FDA list entry with a final decision date, panel, and product code.
- Counts reflect FDA list entries as posted; they do not normalize for device families or company reorganizations.
- "New entrants" indicates the first appearance year of a company or product code in this dataset.
- Time-to-decision uses openFDA 510(k)/PMA records; De Novo entries are excluded due to missing openFDA coverage.
- The view focuses on 2016 onward to highlight the period of accelerated growth.

## Repository structure
- `index.html`: Single-file app (HTML, CSS, JS, embedded data).
- `ai-ml-enabled-devices-xml.xml`: Raw source data download from FDA.
- `data/ai-ml-enabled-devices-enriched.json`: Parsed and enriched dataset.
- `scripts/update_data.py`: Fetches, parses, enriches, and refreshes the dashboard data.
- `.github/workflows/update-data.yml`: Scheduled updater workflow.

## Updating the data
1. Run `python scripts/update_data.py`.
2. The script downloads the XML, refreshes `ai-ml-enabled-devices-xml.xml`, rebuilds the embedded JSON in `index.html`, and writes `data/ai-ml-enabled-devices-enriched.json`.
3. Commit and push to redeploy via GitHub Pages.

## Automation
- GitHub Actions runs a weekly refresh (Monday 14:00 UTC) and can be run manually via the Actions tab.
- The workflow downloads the FDA XML, updates the enriched JSON and dashboard embed, then commits changes back to `main`.

## GitHub Pages
The site is published from the `main` branch at `/`:
https://vishalsachdev.github.io/fda/

## Known limitations
- Product code taxonomy and panel categories are used as-is from FDA.
- Company names may appear with variations across entries.
- Time-to-decision is not available for De Novo entries and may be missing for some PMA supplements.
- No external enrichment (device class, clearance type, modality, geography) is included yet.

## Future enhancements
- Add clearance type (510(k), De Novo, PMA) and device class.
- Add modality/task taxonomy for AI use cases.
- Add company headquarters and geography.
