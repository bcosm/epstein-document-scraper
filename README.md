# Epstein Document Scraper

A hardened tool to search, download, extract text from, and deduplicate documents from the [DOJ Epstein Document Library](https://www.justice.gov/epstein/search).

## What It Does

1. **Search** — Queries the DOJ's internal Elasticsearch API for documents matching your search terms
2. **Download** — Downloads all matching PDFs with retry logic and resume support
3. **Extract** — Converts PDFs to plain text using PyMuPDF
4. **Deduplicate** — Removes near-duplicate documents using MinHash LSH (95% similarity threshold)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install firefox
```

### 2. Run It

**Easiest way** — edit `run.py` and change the `QUERIES` list:

```python
QUERIES = ["passport"]          # ← change this
OUTPUT_DIR = "results"          # ← and optionally this
```

Then run:

```bash
python run.py
```

**Or use the CLI directly:**

```bash
# Single query
python scrape.py "passport"

# Multiple queries (results merged into one folder)
python scrape.py "minor" "children" "trafficking"

# Custom output directory + page limit
python scrape.py "passport" -o passport_docs --max-pages 10

# Re-extract text and deduplicate existing PDFs
python scrape.py --text-only -o existing_folder
```

## CLI Options

| Flag | Description |
|------|-------------|
| `queries` | One or more search terms |
| `-o, --output` | Output directory (default: auto-named) |
| `--max-pages` | Max result pages per query (10 results/page) |
| `--headless` | Run browser in headless mode |
| `--text-only` | Skip scraping; just extract text & dedupe |
| `--no-dedupe` | Skip deduplication step |
| `--dedupe-threshold` | Similarity threshold for dedup (default: 0.95) |

## Output Structure

```
results/
├── pdfs/             # Downloaded PDF files
├── texts/            # Extracted plain text
│   └── removed_duplicates/  # Duplicate texts moved here
└── manifest.json     # Download stats per query
```

## How It Works

The DOJ site has an age-verification gate and bot detection that blocks typical scrapers. This tool:

1. Launches a real **Firefox** browser (Chromium is blocked by the site)
2. Dismisses the age-verification popup via JavaScript
3. Calls the site's internal `/multimedia-search` **Elasticsearch API** directly from the browser context, which carries the session cookies — no fragile click-based pagination
4. Downloads PDFs through the authenticated browser session with concurrency and retries
5. Extracts text with PyMuPDF (fast C-based PDF parser)
6. Deduplicates with MinHash LSH in O(n) time

**Resume support**: Re-running the same query skips already-downloaded PDFs.

## Requirements

- Python 3.10+
- Firefox (installed via Playwright)
- ~50MB disk per 100 PDFs (varies by document size)

## License

Public domain. This tool accesses publicly available government documents.
