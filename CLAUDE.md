# FDA AI/ML-Enabled Medical Devices Dashboard
type: code

## Context
Single-page dashboard that embeds FDA AI/ML device approvals (2016 onward) with openFDA enrichment and optional summary PDF text extraction.

## Current Focus
- Run summary PDF extraction locally and start analysis on extracted text.

## Roadmap
- [x] Build single-page dashboard with filters and charts.
- [x] Enrich data with openFDA submission/decision dates.
- [x] Automate monthly data refresh via GitHub Actions.
- [x] Add summary PDF extraction script and summary links in the device list.
- [x] Run full summary PDF extraction and store text locally (gitignored).
- [x] Add summary URL coverage for all entries and validate link quality.
- [ ] Develop analysis outputs from summary text (topics, keywords, or trends).

## Session Log
### 2026-01-01
- Completed: added summary PDF extraction workflow and summary links in the dashboard; scheduled monthly updater.
- Completed: ran local summary PDF extraction; populated summary URLs across the dataset; kept a small PDF sample for calibration.
- Next: start analysis of the extracted text corpus.
