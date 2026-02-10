# Epstein Document Scraper

A tool to search, download, extract text from, and deduplicate documents from the [DOJ Epstein Document Library](https://www.justice.gov/epstein/search).

> **[Download ZIP](https://github.com/bcosm/epstein-processor/archive/refs/heads/master.zip)** — One-click download, instructions below.

## What It Does

1. **Search** — Queries the DOJ's internal Elasticsearch API for documents matching your search terms
2. **Download** — Downloads all matching PDFs with retry logic and resume support
3. **Extract** — Converts PDFs to plain text using PyMuPDF
4. **Deduplicate** — Removes near-duplicate documents using MinHash LSH (95% similarity threshold)

---

## Easy Mode (Non-Technical Users)

### Prerequisites

1. **Install Python** — Download from [python.org/downloads](https://www.python.org/downloads/)
   - **IMPORTANT**: Check **"Add Python to PATH"** during installation
2. **Download this tool** — [Click here to download the ZIP](https://github.com/bcosm/epstein-processor/archive/refs/heads/master.zip)
3. **Extract the ZIP** to any folder

### Run It

1. Double-click **`run.bat`**
2. It will automatically install everything needed (first run only)
3. Type your search term (e.g. `trump`, `passport`, `minor children`) and press Enter
4. A Firefox window will open — **don't close it** — it's doing the work
5. When it's done, your results are in the `results` folder:
   - `results/pdfs/` — The downloaded PDF documents
   - `results/texts/` — Extracted plain text from each PDF

That's it. Run it again with a different search term anytime.

---

## Advanced Usage (Developers)

### Setup

```bash
pip install -r requirements.txt
playwright install firefox
```

### Quick Run

Edit `run.py` and change the `QUERIES` list:

```python
QUERIES = ["passport"]          # ← change this
OUTPUT_DIR = "results"          # ← and optionally this
```

Then: `python run.py`

### CLI

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

### CLI Options

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
- Windows (for `run.bat`; the Python scripts work on any OS)
- ~50MB disk per 100 PDFs (varies by document size)

## License

Public domain. This tool accesses publicly available government documents.
