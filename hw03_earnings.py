#!/usr/bin/env python3
"""
hw03_earnings.py
MIS3060 HW3, Part 2: Earnings Pipeline (Form 8-K, Item 2.02 - Results of Operations)

What this script does, for Apple, Microsoft, NVIDIA, JPMorgan Chase and Walmart:
  1. Sends every HTTP request with the SEC EDGAR User-Agent header
     "MIS3060 Villanova lcurley@villanova.edu".
  2. Queries https://data.sec.gov/submissions/CIK{cik}.json and keeps 8-K filings
     whose `items` field contains "2.02".
  3. Selects the most recent FOUR of those filings, one per quarter.
  4. For each filing, builds the filing index URL, finds the earnings press release
     exhibit (.htm), downloads it and strips the HTML to plain text.
  5. Extracts quarterly revenue (in millions or billions), diluted EPS, net income
     and the reporting period (e.g. "fourth quarter fiscal 2024").
  6. Prints each row as it is processed:
         [Ticker] | [Period] | Revenue: $X | EPS: $X | Net Income: $X
  7. Saves every row to hw03/earnings_history.csv with the columns
         company, ticker, cik, filing_date, period, revenue_reported,
         eps_diluted, net_income
  8. Stores the string "NOT_FOUND" for any field the regexes cannot extract
     (never a blank cell or None).

A filing whose press release exhibit can't be found does NOT crash the script:
it prints a warning and moves on to the next filing.

Run (with your venv active):
    python hw03_earnings.py          <- from inside the hw03 folder
    python hw03/hw03_earnings.py     <- from the repo root
The CSV is always written next to this script, i.e. hw03/earnings_history.csv.

Requires:  pip install requests beautifulsoup4
"""

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
USER_AGENT = "MIS3060 Villanova lcurley@villanova.edu"
HEADERS = {"User-Agent": USER_AGENT}

REQUEST_PAUSE_SEC = 0.15   # SEC fair-access policy: max 10 requests per second
MAX_RETRIES = 3
REQUEST_TIMEOUT_SEC = 30

TARGET_ITEM = "2.02"       # Item 2.02 - Results of Operations and Financial Condition
FILINGS_PER_COMPANY = 4    # most recent four quarters
NOT_FOUND = "NOT_FOUND"

# CIKs exactly as given in the assignment (not looked up)
COMPANIES = [
    {"company": "Apple Inc.",            "ticker": "AAPL", "cik": "0000320193"},
    {"company": "Microsoft Corporation", "ticker": "MSFT", "cik": "0000789019"},
    {"company": "NVIDIA Corporation",    "ticker": "NVDA", "cik": "0001045810"},
    {"company": "JPMorgan Chase & Co.",  "ticker": "JPM",  "cik": "0000019617"},
    {"company": "Walmart Inc.",          "ticker": "WMT",  "cik": "0000104169"},
]

OUTPUT_CSV = Path(__file__).resolve().parent / "earnings_history.csv"
CSV_COLUMNS = ["company", "ticker", "cik", "filing_date", "period",
               "revenue_reported", "eps_diluted", "net_income"]

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
FILING_INDEX_URL = ("https://www.sec.gov/Archives/edgar/data/"
                    "{cik_int}/{acc_nodash}/{accession}-index.htm")

# Windows terminals can choke on unusual characters; never crash on printing.
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


# ----------------------------------------------------------------------------
# HTTP - the ONLY place requests.get() is called, so the User-Agent header is
# attached to every single request the script makes.
# ----------------------------------------------------------------------------
def sec_get(url):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_PAUSE_SEC)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SEC)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2 * attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            last_error = requests.HTTPError(f"HTTP {resp.status_code} for {url}")
            time.sleep(2 * attempt)
            continue
        resp.raise_for_status()
        return resp
    raise last_error


# ----------------------------------------------------------------------------
# EDGAR submissions API
# ----------------------------------------------------------------------------
def _rows_from_block(block):
    """Turn EDGAR's column-oriented filing arrays into one dict per filing."""
    n = len(block.get("accessionNumber", []))
    blank = [""] * n
    for i in range(n):
        yield {
            "accession": block["accessionNumber"][i],
            "form": block.get("form", blank)[i] or "",
            "filing_date": block.get("filingDate", blank)[i] or "",
            "items": block.get("items", blank)[i] or "",
            "primary_doc": block.get("primaryDocument", blank)[i] or "",
        }


def iter_filings(cik):
    """Yield every filing for a CIK, newest first.

    The API's `recent` block only holds the latest ~1,000 filings. Heavy filers
    (JPMorgan files thousands of prospectus supplements a year) can push a full
    year of 8-Ks out of it, so older pages are fetched only when needed.
    """
    data = sec_get(SUBMISSIONS_URL.format(cik=cik)).json()
    yield from _rows_from_block(data["filings"]["recent"])
    pages = sorted(data["filings"].get("files", []),
                   key=lambda p: p.get("filingTo", ""), reverse=True)
    for page in pages:
        yield from _rows_from_block(
            sec_get(SUBMISSIONS_PAGE_URL.format(name=page["name"])).json())


def has_item(items_field, item_code):
    """True if the comma-separated `items` field contains the item code."""
    return item_code in [part.strip() for part in items_field.split(",")]


def quarter_key(filing_date):
    year, month = int(filing_date[:4]), int(filing_date[5:7])
    return (year, (month - 1) // 3 + 1)


def select_quarterly_filings(cik):
    """Most recent four quarters of Item 2.02 8-Ks.

    Returns a list (newest quarter first) of candidate lists. Each company
    reports earnings once per calendar quarter; if a quarter has more than one
    Item 2.02 8-K (e.g. a pre-announcement), all of them are kept as candidates
    and the one that is actually the earnings release is picked later.
    """
    quarters = {}
    order = []
    for filing in iter_filings(cik):
        if filing["form"] != "8-K" or not has_item(filing["items"], TARGET_ITEM):
            continue
        key = quarter_key(filing["filing_date"])
        if key not in quarters:
            if len(order) == FILINGS_PER_COMPANY:
                break                      # a 5th quarter means the first 4 are complete
            quarters[key] = []
            order.append(key)
        quarters[key].append(filing)
    return [quarters[k] for k in order]


# ----------------------------------------------------------------------------
# Filing index -> press release exhibit
# ----------------------------------------------------------------------------
PRESS_RELEASE_WORDS = re.compile(r"press|release|earnings|results", re.I)


def build_index_url(cik, accession):
    return FILING_INDEX_URL.format(cik_int=int(cik),
                                   acc_nodash=accession.replace("-", ""),
                                   accession=accession)


def find_press_release_url(cik, accession):
    """Return the URL of the earnings press release exhibit (.htm), or None."""
    index_url = build_index_url(cik, accession)
    soup = BeautifulSoup(sec_get(index_url).text, "html.parser")
    candidates = []
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[2].find("a")
        if link is None:
            continue
        href = link.get("href", "")
        if href.startswith("/ix?doc="):          # inline-XBRL viewer wrapper
            href = href[len("/ix?doc="):]
        if not href.lower().endswith((".htm", ".html")):
            continue
        doc_type = cells[3].get_text(strip=True).upper()
        if not doc_type.startswith("EX-99"):
            continue
        description = cells[1].get_text(" ", strip=True)
        rank = (0 if doc_type == "EX-99.1" else 1,
                0 if PRESS_RELEASE_WORDS.search(description) else 1,
                len(candidates))
        candidates.append((rank, urljoin("https://www.sec.gov", href)))
    if not candidates:
        return None
    return min(candidates)[1]


def html_to_text(html):
    """Strip HTML to a single line of clean plain text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "ix:header"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = text.translate({0xA0: " ", 0x200B: "", 0x2019: "'", 0x2018: "'",
                           0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"})
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------------
# Extraction
# ----------------------------------------------------------------------------
NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
TABLE_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?)"     # table cells: 102,466 style
UNIT = r"(billion|million)"
EPS_NUM = r"(\d+\.\d{2})"

# A match is thrown out when the words right around it mark a non-GAAP,
# managed-basis or full-year figure (we want GAAP, reported, quarterly).
REJECT_CONTEXT = re.compile(
    r"adjusted|non-gaap|managed|full[\s-]year|annual|nine[\s-]months|"
    r"twelve[\s-]months|year[\s-]to[\s-]date", re.I)


def earliest_match(text, patterns, check_context=True):
    """Earliest acceptable match across a group of patterns (headline figures
    come first in a press release, segment and comparison figures later)."""
    best = None
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            if check_context:
                context = text[max(0, m.start() - 12): m.start() + 12]
                if REJECT_CONTEXT.search(context):
                    continue
            if best is None or m.start() < best.start():
                best = m
            break
    return best


def table_unit(text):
    """Unit stated in the financial-statement headers, e.g. '(In millions ...'."""
    # Statement headers say "(In millions ...)" / "(Amounts in millions ...)".
    # Prose elsewhere can say "in billions", so the millions/thousands header
    # wins whenever it appears anywhere in the release.
    for unit in ("millions", "thousands", "billions"):
        if re.search(r"\bin\s+" + unit + r"\b", text, re.I):
            return unit.rstrip("s")
    return "million"


# --- Revenue -----------------------------------------------------------------
REVENUE_PROSE = [
    # "Revenue was $77.7 billion" / "quarterly revenue of $94.9 billion"
    r"\b(?:(?:total|net|consolidated|quarterly|reported|record|gaap)\s+)*"
    r"(?:revenues?|net\s+sales)\s+(?:was|were|of|totaled|reached|rose\s+to|"
    r"grew\s+to|increased\s+to|came\s+in\s+at)\s+(?:a\s+record\s+|approximately\s+|"
    r"about\s+)?\$\s*" + NUM + r"\s*" + UNIT + r"\b",
    # NVIDIA: "revenue for the third quarter ended October 26, 2025, of $57.0 billion"
    r"\b(?:revenues?|net\s+sales)\s+for\s+the\s+(?:first|second|third|fourth)[\s-]+"
    r"quarter\b[^$]{0,80}?\$\s*" + NUM + r"\s*" + UNIT + r"\b",
]
REVENUE_TABLE = [
    r"\b(?:total\s+net\s+sales|total\s+net\s+revenues?|total\s+revenues?|"
    r"net\s+revenues?|revenues?)\s*\$\s*" + TABLE_NUM,
]


def extract_revenue(text):
    m = earliest_match(text, REVENUE_PROSE)
    if m:
        return f"{m.group(1)} {m.group(2).lower()}"
    m = earliest_match(text, REVENUE_TABLE)
    if m:
        return f"{m.group(1)} {table_unit(text)}"
    return NOT_FOUND


# --- Diluted EPS ---------------------------------------------------------------
EPS_PROSE = [
    # Apple / Microsoft: "diluted earnings per share of $1.85" / "... was $3.72"
    r"\bdiluted\s+(?:earnings|net\s+income)\s+per\s+(?:common\s+)?share\s+"
    r"(?:was|were|of|totaled)\s+\$\s*" + EPS_NUM,
    # NVIDIA: "GAAP earnings per diluted share for the quarter were $1.30"
    r"\b(?:earnings|net\s+income)\s+per\s+diluted\s+(?:common\s+)?share"
    r"(?:\s+for\s+the\s+(?:quarter|period))?\s+(?:was|were|of)\s+\$\s*" + EPS_NUM,
    # Walmart / JPMorgan: "GAAP EPS of $0.77", "EPS of $5.07"
    r"\b(?:GAAP\s+|diluted\s+)?EPS\s+(?:was|were|of)\s+\$\s*" + EPS_NUM,
    # JPMorgan headline: "net income of $14.4 billion, or $5.07 per share"
    r"(?:,\s*or|\()\s*\$\s*" + EPS_NUM + r"\s+per\s+(?:diluted\s+)?(?:common\s+)?share",
]
EPS_TABLE = [
    r"\bnet\s+income\s+per\s+diluted\s+share\s*\$\s*" + EPS_NUM,
    r"\bdiluted\s+(?:earnings|net\s+income)\s+per\s+(?:common\s+)?share"
    r"[^$\d]{0,60}\$\s*" + EPS_NUM,
    r"\bdiluted\s*\$\s*" + EPS_NUM,
]


def extract_eps(text):
    m = earliest_match(text, EPS_PROSE) or earliest_match(text, EPS_TABLE)
    return m.group(1) if m else NOT_FOUND


# --- Net income ----------------------------------------------------------------
NET_INCOME_PROSE = [
    # Microsoft: "Net income was $27.7 billion"; JPMorgan: "net income of $14.4 billion"
    r"\bnet\s+income(?:\s+attributable\s+to\s+[A-Z][\w.&\s]{0,30}?)?\s+(?:was|were|of|"
    r"totaled|reached|increased\s+to|decreased\s+to)\s+(?:a\s+record\s+|approximately\s+)?"
    r"\$\s*" + NUM + r"\s*" + UNIT + r"\b",
]
NET_INCOME_TABLE = [
    # Walmart: "Consolidated net income attributable to Walmart $ 6,145"
    r"\bnet\s+income\s+attributable\s+to\s+(?!non-?controlling)[A-Za-z.,&\s]{1,30}?"
    r"\s*\$\s*" + TABLE_NUM,
    # Apple / NVIDIA: "Net income $ 27,466"
    r"\bnet\s+income\s*\$\s*" + TABLE_NUM,
]


def extract_net_income(text):
    m = earliest_match(text, NET_INCOME_PROSE)
    if m:
        return f"{m.group(1)} {m.group(2).lower()}"
    for pattern in NET_INCOME_TABLE:          # parent-attributable line wins
        m = earliest_match(text, [pattern])
        if m:
            return f"{m.group(1)} {table_unit(text)}"
    return NOT_FOUND


# --- Reporting period ----------------------------------------------------------
QUARTER_WORDS = {"first": "first", "1st": "first", "1": "first",
                 "second": "second", "2nd": "second", "2": "second",
                 "third": "third", "3rd": "third", "3": "third",
                 "fourth": "fourth", "4th": "fourth", "4": "fourth"}
QW = r"(first|second|third|fourth|1st|2nd|3rd|4th)"


def _year(y):
    y = y.lstrip("'")
    return y if len(y) == 4 else "20" + y


PERIOD_FISCAL = [
    # "third quarter fiscal 2026", "first quarter of fiscal year 2026"
    (QW + r"[\s-]+quarter(?:\s+(?:of|for))?(?:\s+the)?\s+fiscal(?:\s+year)?\s+"
          r"((?:19|20)\d{2}|'?\d{2})\b",
     lambda m: f"{QUARTER_WORDS[m.group(1).lower()]} quarter fiscal {_year(m.group(2))}"),
    # Apple: "fiscal 2025 fourth quarter"
    (r"\bfiscal(?:\s+year)?\s+((?:19|20)\d{2})\s+" + QW + r"[\s-]+quarter",
     lambda m: f"{QUARTER_WORDS[m.group(2).lower()]} quarter fiscal {m.group(1)}"),
    # Walmart: "Q3 FY26", "Q3 fiscal 2026"
    (r"\bQ([1-4])\s*(?:FY|fiscal(?:\s+year)?\s*)\s*('?\d{2,4})\b",
     lambda m: f"{QUARTER_WORDS[m.group(1)]} quarter fiscal {_year(m.group(2))}"),
    # "FY26 Q3"
    (r"\bFY\s*('?\d{2,4})\s*Q([1-4])\b",
     lambda m: f"{QUARTER_WORDS[m.group(2)]} quarter fiscal {_year(m.group(1))}"),
]
PERIOD_CALENDAR = [
    # JPMorgan: "Third-Quarter 2025"
    (QW + r"[\s-]+quarter(?:\s+of)?[\s,]+((?:19|20)\d{2})\b",
     lambda m: f"{QUARTER_WORDS[m.group(1).lower()]} quarter {m.group(2)}"),
]
PERIOD_ENDED = [
    # last resort: "quarter ended September 30, 2025"
    (r"\bquarter\s+ended\s+([A-Z][a-z]+\.?\s+\d{1,2},\s*\d{4})",
     lambda m: f"quarter ended {m.group(1)}"),
]


def extract_period(text):
    for tier in (PERIOD_FISCAL, PERIOD_CALENDAR, PERIOD_ENDED):
        best = None
        for pattern, formatter in tier:
            m = re.search(pattern, text, re.I)
            if m and (best is None or m.start() < best[0].start()):
                best = (m, formatter)
        if best:
            return best[1](best[0])
    return NOT_FOUND


def extract_fields(text):
    return {
        "period": extract_period(text),
        "revenue_reported": extract_revenue(text),
        "eps_diluted": extract_eps(text),
        "net_income": extract_net_income(text),
    }


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def not_found_fields():
    return {"period": NOT_FOUND, "revenue_reported": NOT_FOUND,
            "eps_diluted": NOT_FOUND, "net_income": NOT_FOUND}


def process_quarter(company, candidates):
    """Pick the filing in this quarter that is the earnings release and extract it."""
    cik, ticker = company["cik"], company["ticker"]
    fallback = None
    for filing in candidates:
        accession = filing["accession"]
        try:
            exhibit_url = find_press_release_url(cik, accession)
        except Exception as exc:
            print(f"  WARNING: {ticker} {accession}: could not read filing index "
                  f"({exc}). Skipping this filing.")
            continue
        if exhibit_url is None:
            print(f"  WARNING: {ticker} {accession} ({filing['filing_date']}): no press "
                  f"release exhibit (.htm) in {build_index_url(cik, accession)}. "
                  f"Skipping this filing.")
            continue
        try:
            text = html_to_text(sec_get(exhibit_url).text)
        except Exception as exc:
            print(f"  WARNING: {ticker} {accession}: could not download {exhibit_url} "
                  f"({exc}). Skipping this filing.")
            continue
        fields = extract_fields(text)
        if fields["revenue_reported"] != NOT_FOUND or fields["eps_diluted"] != NOT_FOUND:
            return filing, fields
        if fallback is None:
            fallback = (filing, fields)
    if fallback:
        return fallback
    # Nothing usable in this quarter: keep the row, clearly marked NOT_FOUND.
    return candidates[0], not_found_fields()


def money(value):
    return value if value == NOT_FOUND else f"${value}"


def main():
    rows = []
    for company in COMPANIES:
        ticker = company["ticker"]
        try:
            quarters = select_quarterly_filings(company["cik"])
        except Exception as exc:
            print(f"WARNING: {ticker}: could not query EDGAR submissions API ({exc}). "
                  f"Moving on to the next company.")
            continue
        if not quarters:
            print(f"WARNING: {ticker}: no 8-K filings with Item {TARGET_ITEM} found.")
            continue
        if len(quarters) < FILINGS_PER_COMPANY:
            print(f"NOTE: {ticker}: only {len(quarters)} quarter(s) of Item "
                  f"{TARGET_ITEM} filings found.")

        for candidates in quarters:
            filing, fields = process_quarter(company, candidates)
            row = {
                "company": company["company"],
                "ticker": ticker,
                "cik": company["cik"],
                "filing_date": filing["filing_date"],
                **fields,
            }
            # Guarantee: no blank / None cells, ever.
            row = {k: (v if (v is not None and str(v).strip()) else NOT_FOUND)
                   for k, v in row.items()}
            rows.append(row)
            print(f"{ticker} | {row['period']} | Revenue: {money(row['revenue_reported'])} | "
                  f"EPS: {money(row['eps_diluted'])} | Net Income: {money(row['net_income'])}")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
