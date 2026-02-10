#!/usr/bin/env python3
"""
Epstein Document Scraper — Hardened Edition (v2)
=================================================
Downloads PDFs from the justice.gov Epstein Library search, extracts
text, and deduplicates.  Supports one or more queries in a single run.

Architecture:
  1. Firefox browser loads the search page and dismisses the age gate
     (establishes required session cookies).
  2. The internal Elasticsearch API at /multimedia-search?keys=<q>&page=N
     is called via the browser context (carries cookies automatically).
     Returns JSON with PDF URLs — no fragile click-based pagination.
  3. PDFs are downloaded via the authenticated browser session.
  4. Text is extracted with PyMuPDF and deduplicated with MinHash LSH.

Usage:
    python scrape.py "passport"
    python scrape.py "minor" "children" "trafficking"
    python scrape.py "passport" -o passport_docs --max-pages 10
    python scrape.py --text-only -o existing_docs      # re-extract + dedupe only
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

# ── dependency gate ──────────────────────────────────────────────────────────
MISSING: list[str] = []
try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PwTimeout,
    )
except ImportError:
    MISSING.append("playwright")
try:
    import fitz  # PyMuPDF
except ImportError:
    MISSING.append("pymupdf")
try:
    from datasketch import MinHash, MinHashLSH
except ImportError:
    MISSING.append("datasketch")
if MISSING:
    print(f"Missing packages: {', '.join(MISSING)}")
    print(f"  pip install {' '.join(MISSING)}")
    if "playwright" in MISSING:
        print("  playwright install firefox")
    sys.exit(1)

# ── constants ────────────────────────────────────────────────────────────────
SEARCH_URL = "https://www.justice.gov/epstein/search"
API_URL = "https://www.justice.gov/multimedia-search"  # Elasticsearch endpoint
RESULTS_PER_PAGE = 10
MAX_RETRIES = 3
PAGE_LIMIT_DEFAULT = 9999  # effectively unlimited
CONCURRENT_DOWNLOADS = 4   # parallel download slots
DOWNLOAD_TIMEOUT = 300_000  # 5 minutes per file (some are 100MB+)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# JS that clicks the "Yes" age-verification button.
# The button has NO id — we match by text content.
AGE_VERIFY_JS = """
(() => {
    const btns = [...document.querySelectorAll('button')];
    const yes = btns.find(b => b.textContent.trim() === 'Yes');
    if (yes) { yes.click(); return 'clicked'; }
    return 'not-found';
})()
"""

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
"""


# ── helpers ──────────────────────────────────────────────────────────────────
async def _adelay(lo: float = 0.4, hi: float = 1.2) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


def _safe_filename(url: str) -> str:
    """Derive a filesystem-safe filename from a URL."""
    name = os.path.basename(urlparse(url).path)
    if name and name.lower().endswith(".pdf"):
        return re.sub(r'[<>:"/\\|?*]', "_", name)
    return hashlib.md5(url.encode()).hexdigest()[:16] + ".pdf"


# ── browser session ──────────────────────────────────────────────────────────
class BrowserSession:
    """Manages the Playwright browser lifecycle."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self.browser: Browser | None = None
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        self._pw = await async_playwright().start()
        for engine in ("firefox", "chromium"):
            try:
                launcher = getattr(self._pw, engine)
                self.browser = await launcher.launch(
                    headless=self.headless,
                    slow_mo=40,
                )
                print(f"  [browser] {engine} ({'headless' if self.headless else 'headed'})")
                break
            except Exception as exc:
                print(f"  [browser] {engine} unavailable: {exc}")
        if not self.browser:
            raise RuntimeError("No browser available. Run: playwright install firefox")

        self.ctx = await self.browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await self.ctx.add_init_script(STEALTH_JS)
        self.page = await self.ctx.new_page()
        self.page.set_default_timeout(30_000)
        self.page.set_default_navigation_timeout(60_000)
        return self.page

    async def close(self) -> None:
        for obj in (self.page, self.ctx, self.browser):
            try:
                if obj:
                    await obj.close()
            except Exception:
                pass
        if self._pw:
            await self._pw.stop()

    async def goto(self, url: str, retries: int = MAX_RETRIES) -> bool:
        for attempt in range(1, retries + 1):
            try:
                resp = await self.page.goto(url, wait_until="domcontentloaded")
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15_000)
                except PwTimeout:
                    pass
                if resp and resp.status >= 400:
                    print(f"    HTTP {resp.status} – retry {attempt}/{retries}")
                    await _adelay(3, 6)
                    continue
                return True
            except PwTimeout:
                print(f"    timeout – retry {attempt}/{retries}")
                await _adelay(2, 5)
            except Exception as exc:
                print(f"    nav error ({exc}) – retry {attempt}/{retries}")
                await _adelay(2, 4)
        return False

    async def dismiss_age_gate(self) -> bool:
        """Click 'Yes' on the age-verification dialog."""
        for _ in range(5):
            try:
                result = await self.page.evaluate(AGE_VERIFY_JS)
                if result == "clicked":
                    print("    [verify] age-gate dismissed")
                    await _adelay(1.5, 3.0)
                    return True
            except Exception:
                pass
            await _adelay(0.5, 1.0)
        return False

    async def init_session(self) -> bool:
        """Load the search page and pass the age gate to establish cookies."""
        print(f"  [init] loading {SEARCH_URL}")
        if not await self.goto(SEARCH_URL):
            print("  ERROR: cannot load search page")
            return False
        await self.dismiss_age_gate()
        print("  [init] session established")
        return True


# ── API-based search ─────────────────────────────────────────────────────────
class EpsteinScraper:
    """
    Uses the internal /multimedia-search Elasticsearch API to find PDF URLs.
    The API requires authenticated cookies from the age-gate session.

    API response structure:
        {
          "hits": {
            "total": {"value": 1545},
            "hits": [
              {"_source": {"ORIGIN_FILE_URI": "https://...pdf", "ORIGIN_FILE_NAME": "..."}},
              ...
            ]
          }
        }
    Each page returns up to 10 results. Page parameter is 1-indexed.
    """

    def __init__(self, session: BrowserSession, max_pages: int = PAGE_LIMIT_DEFAULT):
        self.s = session
        self.max_pages = max_pages

    async def _api_fetch(self, query: str, page: int) -> dict | None:
        """Fetch one page of API results via the browser context (uses cookies)."""
        url = f"{API_URL}?keys={quote(query)}&page={page}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = await self.s.page.evaluate(f"""
                    async () => {{
                        const r = await fetch({json.dumps(url)});
                        if (!r.ok) return {{ error: r.status }};
                        return await r.json();
                    }}
                """)
                if isinstance(data, dict) and "error" in data:
                    print(f"    API HTTP {data['error']} page={page} attempt={attempt}")
                    await _adelay(2, 4)
                    continue
                return data
            except Exception as exc:
                print(f"    API error page={page} attempt={attempt}: {exc}")
                await _adelay(2, 4)
        return None

    async def search(self, query: str) -> list[str]:
        """Query the API and collect all PDF URLs across pages."""
        print(f"  [search] querying API: {query!r}")

        # First page — also tells us the total
        data = await self._api_fetch(query, 1)
        if not data or "hits" not in data:
            print("  ERROR: API returned no data")
            return []

        total = data["hits"]["total"]["value"]
        total_pages = min(math.ceil(total / RESULTS_PER_PAGE), self.max_pages)
        print(f"  [search] {total} index entries  ({total_pages} pages, capped at {self.max_pages})")
        print(f"           (many entries reference the same PDF — unique count will be lower)")

        # Collect URLs from first page
        all_urls: set[str] = set()
        self._extract_urls(data, all_urls)
        print(f"    page 1/{total_pages}: {len(all_urls)} links")

        # Remaining pages
        for pg in range(2, total_pages + 1):
            await _adelay(0.3, 0.8)  # polite pacing
            page_data = await self._api_fetch(query, pg)
            if not page_data or "hits" not in page_data:
                print(f"    page {pg}/{total_pages}: API error, stopping")
                break
            before = len(all_urls)
            self._extract_urls(page_data, all_urls)
            added = len(all_urls) - before
            if pg % 20 == 0 or pg == total_pages:
                print(f"    page {pg}/{total_pages}: +{added}  (total {len(all_urls)})")
            if added == 0:
                # No new results — remaining entries all reference already-seen PDFs
                print(f"    page {pg}: 0 new unique PDFs, all remaining are duplicates — stopping")
                break

        print(f"  [search] collected {len(all_urls)} unique PDF URLs")
        return sorted(all_urls)

    @staticmethod
    def _extract_urls(data: dict, target: set[str]) -> None:
        """Pull PDF URLs from Elasticsearch response."""
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            uri = src.get("ORIGIN_FILE_URI", "")
            if uri and ".pdf" in uri.lower():
                target.add(uri)

    async def download(self, urls: list[str], dest: Path) -> tuple[int, int, int]:
        """Download PDFs with concurrency. Returns (downloaded, skipped, failed)."""
        dest.mkdir(parents=True, exist_ok=True)
        dl, sk, fa = 0, 0, 0
        sem = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

        async def _dl_one(url: str) -> str:
            """Returns 'dl', 'skip', or 'fail'."""
            fname = _safe_filename(url)
            out = dest / fname
            if out.exists() and out.stat().st_size > 500:
                return "skip"

            async with sem:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        resp = await self.s.page.request.get(url, timeout=DOWNLOAD_TIMEOUT)
                        if resp.ok:
                            data = await resp.body()
                            if len(data) > 500:
                                out.write_bytes(data)
                                return "dl"
                            else:
                                print(f"    tiny response for {fname} ({len(data)}B)")
                        else:
                            print(f"    HTTP {resp.status} for {fname} (attempt {attempt})")
                    except Exception as exc:
                        print(f"    err {fname} (attempt {attempt}): {exc}")
                    await _adelay(1.0, 2.5)
            return "fail"

        # Process in batches to give progress updates
        batch_size = 25
        for start in range(0, len(urls), batch_size):
            batch = urls[start : start + batch_size]
            results = await asyncio.gather(*[_dl_one(u) for u in batch])
            for r in results:
                if r == "dl":
                    dl += 1
                elif r == "skip":
                    sk += 1
                else:
                    fa += 1
            done = min(start + batch_size, len(urls))
            print(f"    [{done}/{len(urls)}] dl={dl}  skip={sk}  fail={fa}")
            # Brief pause between batches
            if done < len(urls):
                await _adelay(0.2, 0.6)

        return dl, sk, fa


# ── text extraction ──────────────────────────────────────────────────────────
def extract_texts(pdf_dir: Path, txt_dir: Path) -> tuple[int, int]:
    txt_dir.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    for i, p in enumerate(pdfs, 1):
        out = txt_dir / (p.stem + ".txt")
        if out.exists() and out.stat().st_size > 0:
            ok += 1
            continue
        try:
            doc = fitz.open(p)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            if text.strip():
                out.write_text(text, encoding="utf-8")
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        if i % 100 == 0 or i == len(pdfs):
            print(f"    [{i}/{len(pdfs)}] ok={ok}  fail={fail}")
    return ok, fail


# ── deduplication ────────────────────────────────────────────────────────────
def deduplicate(txt_dir: Path, threshold: float = 0.95, num_perm: int = 128) -> tuple[int, int]:
    dupes_dir = txt_dir / "removed_duplicates"
    dupes_dir.mkdir(parents=True, exist_ok=True)
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    files = sorted(txt_dir.glob("*.txt"))
    dupes: list[Path] = []

    for i, f in enumerate(files, 1):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            if len(text.strip()) < 80:
                continue
            m = MinHash(num_perm=num_perm)
            words = text.lower().split()
            for j in range(len(words) - 2):
                m.update(" ".join(words[j : j + 3]).encode())
            if lsh.query(m):
                dupes.append(f)
            else:
                lsh.insert(str(f), m)
        except Exception:
            pass
        if i % 200 == 0:
            print(f"    [{i}/{len(files)}] dupes={len(dupes)}")

    for d in dupes:
        try:
            shutil.move(str(d), str(dupes_dir / d.name))
        except Exception:
            pass

    unique = len(files) - len(dupes)
    print(f"    unique={unique}  dupes={len(dupes)}")
    return unique, len(dupes)


# ── manifest (resume support) ────────────────────────────────────────────────
def load_manifest(out: Path) -> dict:
    p = out / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_manifest(out: Path, data: dict) -> None:
    (out / "manifest.json").write_text(json.dumps(data, indent=2))


# ── CLI ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scrape",
        description="Search the DOJ Epstein Library, download PDFs, extract text, deduplicate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scrape.py "passport"
  python scrape.py "minor" "children" "trafficking"
  python scrape.py "passport" -o passport_docs --max-pages 5
  python scrape.py --text-only -o existing_docs
""",
    )
    p.add_argument("queries", nargs="*", help='Search terms (e.g. "minor" "children").')
    p.add_argument("-o", "--output", default=None, help="Output directory.")
    p.add_argument("--max-pages", type=int, default=PAGE_LIMIT_DEFAULT, help="Max result pages per query.")
    p.add_argument("--headless", action="store_true", help="Headless mode (may be blocked).")
    p.add_argument("--text-only", action="store_true", help="Skip scraping; extract text & dedupe existing PDFs.")
    p.add_argument("--no-dedupe", action="store_true", help="Skip deduplication.")
    p.add_argument("--dedupe-threshold", type=float, default=0.95, help="Similarity threshold (default 0.95).")
    return p


async def run(args: argparse.Namespace) -> None:
    queries: list[str] = args.queries

    if args.output:
        out = Path(args.output)
    elif len(queries) == 1:
        out = Path(f"{queries[0].strip().replace(' ', '_')}_results")
    elif queries:
        out = Path("multi_results")
    else:
        out = Path("scraped_output")

    pdf_dir = out / "pdfs"
    txt_dir = out / "texts"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)

    bar = "=" * 64
    print(bar)
    print("  EPSTEIN DOCUMENT SCRAPER  v2 (API-based)")
    print(bar)
    print(f"  queries  : {queries or '(text-only mode)'}")
    print(f"  output   : {out}")
    print(f"  max pages: {args.max_pages}")
    print(f"  headless : {args.headless}")
    print(bar)

    stats: list[dict] = []

    if not args.text_only and queries:
        session = BrowserSession(headless=args.headless)
        try:
            await session.start()
            if not await session.init_session():
                print("FATAL: could not establish session. Exiting.")
                return
            scraper = EpsteinScraper(session, max_pages=args.max_pages)

            for q in queries:
                print(f"\n{'─' * 64}")
                print(f"  QUERY: {q}")
                print(f"{'─' * 64}")

                urls = await scraper.search(q)
                dl, sk, fa = 0, 0, 0
                if urls:
                    dl, sk, fa = await scraper.download(urls, pdf_dir)
                else:
                    print("  no results")

                qstat = {"query": q, "links": len(urls), "dl": dl, "skip": sk, "fail": fa}
                stats.append(qstat)
                manifest = load_manifest(out)
                manifest[q] = qstat
                save_manifest(out, manifest)
        finally:
            await session.close()

    print(f"\n{'─' * 64}")
    print("  TEXT EXTRACTION")
    print(f"{'─' * 64}")
    ext_ok, ext_fail = extract_texts(pdf_dir, txt_dir)

    unique, dupes = 0, 0
    if not args.no_dedupe:
        print(f"\n{'─' * 64}")
        print("  DEDUPLICATION")
        print(f"{'─' * 64}")
        unique, dupes = deduplicate(txt_dir, threshold=args.dedupe_threshold)
    else:
        unique = len(list(txt_dir.glob("*.txt")))

    print(f"\n{bar}")
    print("  RESULTS SUMMARY")
    print(bar)
    for s in stats:
        print(f"  query={s['query']!r:20s}  links={s['links']:5d}  "
              f"dl={s['dl']:4d}  skip={s['skip']:4d}  fail={s['fail']:3d}")
    if stats:
        print(f"  {'─' * 56}")
    print(f"  PDFs on disk  : {len(list(pdf_dir.glob('*.pdf')))}")
    print(f"  Texts created : {ext_ok}  (failed: {ext_fail})")
    print(f"  Unique texts  : {unique}")
    print(f"  Dupes removed : {dupes}")
    print(f"  Output dir    : {out.resolve()}")
    print(bar)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.queries and not args.text_only:
        parser.print_help()
        print("\nError: provide at least one query, or use --text-only.")
        sys.exit(1)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
