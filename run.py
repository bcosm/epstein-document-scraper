#!/usr/bin/env python3
"""
=== EPSTEIN DOCUMENT PIPELINE ===

Edit the settings below, then run:
    python run.py

That's it. The full pipeline (search → download → extract text → deduplicate)
will execute automatically.
"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  EDIT THESE                                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

QUERIES = ["passport"]          # Add/change queries here
OUTPUT_DIR = "results"          # Output folder name
MAX_PAGES = 9999                # Max pages per query (10 results/page), 9999 = all

# ╔══════════════════════════════════════════════════════════════════╗
# ║  DON'T EDIT BELOW THIS LINE                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

import subprocess
import sys
from pathlib import Path

script = Path(__file__).parent / "scrape.py"
python = sys.executable

cmd = [python, str(script)] + QUERIES + ["-o", OUTPUT_DIR, "--max-pages", str(MAX_PAGES)]
print(f"Running: {' '.join(cmd)}\n")
sys.exit(subprocess.call(cmd))
