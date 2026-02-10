#!/bin/bash
# ================================================================
#   EPSTEIN DOCUMENT SCRAPER - One-Click Setup (macOS/Linux)
# ================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================"
echo "  EPSTEIN DOCUMENT SCRAPER - One-Click Setup"
echo "================================================================"
echo ""

# ── Locate Python ────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | awk '{print $2}')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            echo "  Python found: $ver ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  [ERROR] Python 3.10+ is required but not found."
    echo ""
    echo "  Install Python:"
    echo "    macOS:  brew install python3"
    echo "    Ubuntu: sudo apt install python3 python3-venv python3-pip"
    echo ""
    exit 1
fi

# ── Create virtual environment if needed ─────────────────────────
if [ ! -f ".venv/bin/python" ]; then
    echo "  Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

source .venv/bin/activate
PYTHON=".venv/bin/python"
PIP=".venv/bin/pip"

# ── Install dependencies ────────────────────────────────────────
echo "  Installing dependencies (this may take a minute on first run)..."
"$PIP" install --quiet --upgrade pip 2>/dev/null || true
"$PIP" install --quiet -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "  Retrying with output..."
    "$PIP" install -r "$SCRIPT_DIR/requirements.txt"
fi

# ── Install Firefox browser ─────────────────────────────────────
echo "  Checking Firefox browser for Playwright..."
.venv/bin/playwright install firefox 2>/dev/null || "$PYTHON" -m playwright install firefox
echo "  All dependencies ready."

# ── Ask for search query ─────────────────────────────────────────
echo ""
echo "================================================================"
echo "  SETUP COMPLETE - Ready to search"
echo "================================================================"
echo ""
echo "  Enter search terms, separated by commas for multiple queries."
echo "  Examples:"
echo "    passport"
echo "    trump"
echo "    minor, children, trafficking"
echo ""
read -p "  Search for: " QUERY

if [ -z "$QUERY" ]; then
    echo ""
    echo "  [ERROR] No search term entered. Exiting."
    exit 1
fi

# ── Parse comma-separated queries into arguments ────────────────
ARGS=()
IFS=',' read -ra PARTS <<< "$QUERY"
for part in "${PARTS[@]}"; do
    trimmed=$(echo "$part" | xargs)  # trim whitespace
    if [ -n "$trimmed" ]; then
        ARGS+=("$trimmed")
    fi
done

# ── Run the scraper ──────────────────────────────────────────────
echo ""
echo "  Starting scraper for: ${ARGS[*]}"
echo "  (A Firefox window will open - don't close it!)"
echo ""

"$PYTHON" "$SCRIPT_DIR/scrape.py" "${ARGS[@]}" -o results

echo ""
echo "================================================================"
echo "  DONE! Results are in the 'results' folder:"
echo "    results/pdfs/    - Downloaded PDF files"
echo "    results/texts/   - Extracted plain text"
echo "================================================================"
echo ""
