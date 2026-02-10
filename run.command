#!/bin/bash
# ================================================================
#   EPSTEIN DOCUMENT SCRAPER - Double-click to run (macOS)
# ================================================================
# This file auto-detects its own directory, so you can double-click
# it from Finder without needing to open Terminal or cd anywhere.

# cd to the directory where this script lives
cd "$(dirname "$0")"

# Run the main setup/scraper script
bash run.sh

# Keep Terminal open so user can see results
echo ""
echo "Press any key to close this window..."
read -n 1
