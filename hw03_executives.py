#!/usr/bin/env python3
"""
hw03_executives.py
MIS3060 HW3, Part 3: Executive Events Pipeline (Form 8-K, Item 5.02 -
Departure of Directors or Certain Officers; Election of Directors;
Appointment of Certain Officers)

What this script does, for Apple, Microsoft, NVIDIA, JPMorgan Chase and Walmart:
  1. Sends every HTTP request with the SEC EDGAR User-Agent header
     "MIS3060 Villanova lcurley@villanova.edu".
  2. Queries https://data.sec.gov/submissions/CIK{cik}.json and keeps 8-K filings
     whose `items` field contains "5.02" AND whose `filingDate` is within the
     past 12 months.
  3. Downloads each matching 8-K, strips the HTML and extracts, for every person
     the Item 5.02 section reports on:
         event type ("departure", "appointment" or "both"),
         full name, title, effective date of the change.
     "both" = the same person leaves one role and takes another in the filing
     (e.g. steps down as CEO and becomes Executive Chair).
  4. Creates a SEPARATE row for each event, so a filing with one departure and
     one appointment produces two rows.
  5. Prints each event as it is processed:
         [Ticker] | [Date] | [Event Type] | [Name] | [Title]
  6. Prints "[Ticker]: No executive events in past 12 months" for any company
     with no Item 5.02 filings in the window. That is valid data, not an error.
  7. Saves every event to hw03/executive_events.csv with the columns
         company, ticker, cik, filing_date, event_type, person_name, title,
         effective_date

Title or effective date that can't be extracted is stored as "NOT_FOUND"
(same convention as the earnings pipeline). Dates are stored as YYYY-MM-DD.
Some Item 5.02 filings only cover compensation (Item 5.02(e)) and name no
departure or appointment; those are reported on screen and produce no row.

Run (with your venv active):
    python hw03_executives.py          <- from inside the hw03 folder
    python hw03/hw03_executives.py     <- from the repo root
The CSV is always written next to this script, i.e. hw03/executive_events.csv.

Requires:  pip install requests beautifulsoup4
"""

import csv
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

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

TARGET_ITEM = "5.02"
LOOKBACK_DAYS = 365        # "past 12 months"
NOT_FOUND = "NOT_FOUND"

# CIKs exactly as given in the assignment (not looked up)
COMPANIES = [
    {"company": "Apple Inc.",            "ticker": "AAPL", "cik": "0000320193"},
    {"company": "Microsoft Corporation", "ticker": "MSFT", "cik": "0000789019"},
    {"company": "NVIDIA Corporation",    "ticker": "NVDA", "cik": "0001045810"},
    {"company": "JPMorgan Chase & Co.",  "ticker": "JPM",  "cik": "0000019617"},
    {"company": "Walmart Inc.",          "ticker": "WMT",  "cik": "0000104169"},
]

OUTPUT_CSV = Path(__file__).resolve().parent / "executive_events.csv"
CSV_COLUMNS = ["company", "ticker", "cik", "filing_date", "event_type",
               "person_name", "title", "effective_date"]

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"

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
    """Yield every filing for a CIK, newest first (fetches older pages only if
    the `recent` block doesn't reach back far enough, e.g. for JPMorgan)."""
    data = sec_get(SUBMISSIONS_URL.format(cik=cik)).json()
    yield from _rows_from_block(data["filings"]["recent"])
    pages = sorted(data["filings"].get("files", []),
                   key=lambda p: p.get("filingTo", ""), reverse=True)
    for page in pages:
        yield from _rows_from_block(
            sec_get(SUBMISSIONS_PAGE_URL.format(name=page["name"])).json())


def has_item(items_field, item_code):
    return item_code in [part.strip() for part in items_field.split(",")]


def recent_502_filings(cik, cutoff_iso):
    matches = []
    for filing in iter_filings(cik):
        if filing["filing_date"] < cutoff_iso:
            break                              # newest-first: everything after is older
        if filing["form"] == "8-K" and has_item(filing["items"], TARGET_ITEM):
            matches.append(filing)
    return matches


def filing_doc_url(cik, filing):
    return ARCHIVES_URL.format(cik_int=int(cik),
                               acc_nodash=filing["accession"].replace("-", ""),
                               doc=filing["primary_doc"])


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "ix:header"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = text.translate({0xA0: " ", 0x200B: "", 0x2019: "'", 0x2018: "'",
                           0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"})
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------------
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
DATE_RE = (r"(?:January|February|March|April|May|June|July|August|September|October|"
           r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"
           r"\s+\d{1,2},\s*\d{4}")


def to_iso(date_text):
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4})", date_text)
    if not m:
        return NOT_FOUND
    word = m.group(1).lower()
    month = next((num for name, num in MONTHS.items() if name.startswith(word[:3])), None)
    try:
        return date(int(m.group(3)), month, int(m.group(2))).isoformat()
    except (TypeError, ValueError):
        return NOT_FOUND


ITEM_502_HEADING = re.compile(
    r"Departure\s+of\s+Directors\s+or\s+(?:Certain\s+)?Officers;?\s*"
    r"(?:Election\s+of\s+Directors;?\s*)?(?:Appointment\s+of\s+(?:Certain\s+)?Officers;?\s*)?"
    r"(?:Compensatory\s+Arrangements\s+of\s+Certain\s+Officers\.?)?", re.I)


def item_502_section(text):
    """Just the Item 5.02 part of the 8-K (stops at the next Item or signatures)."""
    for m in re.finditer(r"[Ii]tem\s*5\.02", text):
        rest = text[m.end():]
        end = re.search(r"[Ii]tem\s*(?!5\.02)\d{1,2}\.\d{2}\b|SIGNATURES?\b", rest)
        section = rest[:end.start()] if end else rest
        if len(section) > 150:
            return ITEM_502_HEADING.sub(" ", section, count=1)
    return text


ABBREVIATIONS = ["Inc.", "Corp.", "Co.", "Ltd.", "Mr.", "Ms.", "Mrs.", "Dr.", "Jr.",
                 "Sr.", "No.", "St.", "U.S.", "N.A.", "L.P.", "LLC.", "Messrs."]


def split_sentences(text):
    protected = text
    for abbr in ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", "<DOT>"))
    # middle/first initials like "John R. Furner", "C. Douglas McMillon"
    protected = re.sub(r"\b([A-Z])\.(?=\s+[A-Z])", r"\1<DOT>", protected)
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z\"(])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


# Capitalized words that are never part of a person's name in an 8-K.
NAME_STOPWORDS = set("""
on in as at by of the a an and or for to from with upon following effective pursuant
this that such each his her their its our we he she they it these those there
mr ms mrs dr messrs
company corporation corp inc co ltd llc group holdings firm bank banking na
apple microsoft nvidia walmart jpmorgan chase morgan sam's club international
board directors director committee compensation audit nominating governance
chief executive officer officers president vice senior principal financial operating
accounting technology information legal general counsel secretary treasurer controller
chair chairman chairwoman chairperson lead independent interim acting global worldwide
human resources people corporate marketing operations services consumer commercial
retail wholesale investment asset wealth management community risk strategy product
products engineering hardware software cloud data center gaming automotive research
item items form report current exhibit exhibits section act securities exchange
commission annual meeting shareholders stockholders plan plans agreement agreements
letter offer award awards equity incentive stock restricted units retirement severance
policy program sec edgar gaap
achievement target targets transition date dates opportunity base named effective
period term performance goal goals bonus salary cash payment
january february march april may june july august september october november december
monday tuesday wednesday thursday friday
new york california washington arkansas texas delaware santa clara cupertino redmond
bentonville united states america north south east west
""".split())

NAME_TOKEN = r"(?:[A-Z]\.|[A-Z][a-zA-Z'\-]*[a-z])"
CAP_RUN = re.compile(NAME_TOKEN + r"(?:\s+" + NAME_TOKEN + r")*")


def find_names(sentence):
    """Return [(name, start, end)] for person names in a sentence."""
    names = []
    for run in CAP_RUN.finditer(sentence):
        tokens = [(t.group(0), run.start() + t.start(), run.start() + t.end())
                  for t in re.finditer(NAME_TOKEN, run.group(0))]
        group = []
        for tok in tokens + [None]:
            is_stop = tok is None or tok[0].rstrip(".").lower() in NAME_STOPWORDS
            if not is_stop:
                group.append(tok)
                continue
            # close the current group
            while group and len(group[-1][0]) == 2 and group[-1][0].endswith("."):
                group.pop()                     # can't end on an initial
            real_words = [g for g in group if not g[0].endswith(".")]
            if 2 <= len(real_words) and len(group) <= 5:
                names.append((" ".join(g[0] for g in group), group[0][1], group[-1][2]))
            group = []
    return names


# ----------------------------------------------------------------------------
# Event / title / date detection
# ----------------------------------------------------------------------------
DEPARTURE_WORDS = re.compile(
    r"\b(?:retire[sd]?|retiring|retirement|resign(?:s|ed|ing|ation)?|"
    r"step(?:s|ped|ping)?\s+down|depart(?:s|ed|ing|ure)?|"
    r"leav(?:e|es|ing)\s+(?:the\s+)?(?:Company|Board|Firm)|will\s+leave|"
    r"terminat(?:e|ed|ion)|separat(?:e|ed|ion)\s+from|"
    r"not\s+(?:to\s+)?(?:stand|seek)\s+(?:for\s+)?re-?election|"
    r"cease[sd]?\s+to\s+serve|will\s+no\s+longer\s+serve|transition(?:s|ing)?\s+out)\b",
    re.I)
DEPARTURE_BEFORE_NAME = re.compile(
    r"(?:retirement|departure|resignation|separation|termination|exit)\s+of\s+"
    r"(?:(?:Mr|Ms|Mrs|Dr)\.\s+)?$", re.I)
# Words after an appointee that are about the person they replace, not them.
SUCCESSION_CUT = re.compile(
    r"\b(?:to\s+succeed|will\s+succeed|succeeding|replac(?:e|es|ing)|successor\s+to|"
    r"following\s+(?:the|his|her)|upon\s+(?:the|his|her))\b", re.I)

APPOINTMENT_BEFORE_NAME = re.compile(
    r"\b(?:appoint(?:ed|s|ing|ment\s+of)?|nam(?:ed|es|ing)|elect(?:ed|s|ing|ion\s+of)?|"
    r"promot(?:ed|es|ing|ion\s+of)|hir(?:ed|es|ing)|select(?:ed|s|ing)?|welcom(?:ed|es))\b",
    re.I)
APPOINTMENT_AFTER_NAME = re.compile(
    r"\b(?:(?:has\s+been|have\s+been|was|were|will\s+be|is\s+being|to\s+be|had\s+been)\s+"
    r"(?:appointed|named|elected|promoted|hired|selected)|"
    r"will\s+(?:succeed|join|become|serve\s+as|assume)|to\s+succeed|"
    r"has\s+(?:joined|accepted)|joins|joined\s+the)\b", re.I)

TITLE_SPAN = r"[A-Z][\w&'\-]*(?:(?:\s+|\s*,\s*)(?:(?:and|of|for|&)\s+)?[A-Z][\w&'\-]*)*"
TITLE_KEYWORDS = re.compile(
    r"\b(?:Chief|President|Chair\w*|Director|Counsel|Secretary|Treasurer|Controller|"
    r"Officer|Head|CEO|CFO|COO|CTO|CAO|Partner|Principal)\b")
POSSESSIVE = r"(?:the\s+|our\s+|its\s+|a\s+|an\s+)?(?:Company's\s+|[A-Z][\w.&]*'s\s+)?"

TITLE_AFTER_NAME = [
    re.compile(r"^\s*,\s*" + POSSESSIVE + r"((?:interim\s+|acting\s+)?" + TITLE_SPAN + ")"),
    re.compile(r"\bas\s+" + POSSESSIVE + r"(?:new\s+)?((?:interim\s+|acting\s+)?" +
               TITLE_SPAN + ")"),
    re.compile(r"\b(?:position|role|office|post)s?\s+(?:as|of)\s+" + POSSESSIVE +
               r"((?:interim\s+|acting\s+)?" + TITLE_SPAN + ")"),
    # "has been named Chief Financial Officer", "was promoted to President"
    re.compile(r"\b(?:appointed|named|elected|promoted|hired|selected)\s+"
               r"(?:to\s+serve\s+as\s+|to\s+the\s+(?:position|role)\s+of\s+|to\s+|as\s+)?" +
               POSSESSIVE + r"((?:interim\s+|acting\s+)?" + TITLE_SPAN + ")"),
]
BOARD_ROLE = re.compile(
    r"\b(?:to|on|from|of)\s+the\s+(?:Company's\s+)?Board\b|"
    r"\bas\s+(?:a\s+|an\s+)?(?:independent\s+)?(?:member\s+of\s+the\s+Board|director)\b|"
    r"re-?election", re.I)
TITLE_BEFORE_NAME = re.compile(r"(" + TITLE_SPAN + r")\s*,?\s*$")


def clean_title(raw, other_names):
    title = raw
    for name in other_names:                 # "Chief Executive Officer, Jane Doe" -> cut
        if name in title:
            title = title[:title.index(name)]
    title = re.sub(r"^[A-Z][\w.&]*'s\s+", "", title)          # drop "Company's "
    title = re.sub(r"[\s,]+(?:and|of|for|&)?\s*$", "", title).strip(" ,")
    words = title.split()
    if len(words) > 15:
        title = " ".join(words[:15])
    return title if TITLE_KEYWORDS.search(title) else None


def find_title(prefix, suffix, other_names):
    window = suffix[:300]
    best = None
    for pattern in TITLE_AFTER_NAME:
        for m in pattern.finditer(window):
            title = clean_title(m.group(1), other_names)
            if title:
                if best is None or m.start() < best[0]:
                    best = (m.start(), title)
                break
    board = BOARD_ROLE.search(window)
    if board and (best is None or board.start() < best[0]):
        best = (board.start(), "Director")
    if best:
        return best[1]
    m = TITLE_BEFORE_NAME.search(prefix[-150:])
    if m:
        title = clean_title(m.group(1), other_names)
        if title:
            return title
    return NOT_FOUND


EFFECTIVE_DATE = re.compile(
    r"\beffective\s+(?:as\s+of\s+)?(?:the\s+close\s+of\s+business\s+)?(?:on\s+)?"
    r"(" + DATE_RE + ")", re.I)
ON_DATE = re.compile(r"\b(?:on|as\s+of)\s+(" + DATE_RE + ")", re.I)
EFFECTIVE_NOW = re.compile(r"\beffective\s+immediately\b", re.I)


def find_effective_date(prefix, suffix, sentence, filing_text):
    for source in (suffix, prefix):
        m = EFFECTIVE_DATE.search(source)
        if m:
            return to_iso(m.group(1))
    m = ON_DATE.search(suffix)
    if m:
        return to_iso(m.group(1))
    if EFFECTIVE_NOW.search(suffix) or EFFECTIVE_NOW.search(prefix):
        # "effective immediately" -> the event date stated in the filing
        m = re.search(r"\bOn\s+(" + DATE_RE + ")", sentence) or \
            re.search(r"\bOn\s+(" + DATE_RE + ")", filing_text)
        if m:
            return to_iso(m.group(1))
    return NOT_FOUND


def surname_key(name):
    words = [w for w in name.split() if not w.endswith(".") and
             w.rstrip(",") not in ("Jr", "Sr", "II", "III", "IV")]
    return words[-1].lower() if words else name.lower()


def extract_events(filing_text):
    """Return a list of events: dicts with event_type, person_name, title, effective_date."""
    section = item_502_section(filing_text)
    people = {}      # surname -> accumulated info, in order of first appearance
    for sentence in split_sentences(section):
        names = find_names(sentence)
        all_names = [n[0] for n in names]
        for i, (name, start, end) in enumerate(names):
            prev_end = names[i - 1][2] if i > 0 else 0
            next_start = names[i + 1][1] if i + 1 < len(names) else len(sentence)
            prefix = sentence[max(prev_end, start - 150):start]
            suffix = sentence[end:next_start]

            departure_zone = SUCCESSION_CUT.split(suffix, maxsplit=1)[0]
            departing = bool(DEPARTURE_WORDS.search(departure_zone) or
                             DEPARTURE_BEFORE_NAME.search(prefix))
            appointed = bool(APPOINTMENT_BEFORE_NAME.search(prefix) or
                             APPOINTMENT_AFTER_NAME.search(suffix))
            if not (departing or appointed):
                continue

            others = [n for n in all_names if n != name]
            key = surname_key(name)
            person = people.setdefault(key, {
                "person_name": name, "departure": False, "appointment": False,
                "title": NOT_FOUND, "effective_date": NOT_FOUND})
            if len(name) > len(person["person_name"]):
                person["person_name"] = name          # keep the fullest form
            person["departure"] |= departing
            person["appointment"] |= appointed
            if person["title"] == NOT_FOUND:
                person["title"] = find_title(prefix, suffix, others)
            if person["effective_date"] == NOT_FOUND:
                person["effective_date"] = find_effective_date(prefix, suffix, sentence,
                                                               filing_text)
    events = []
    for person in people.values():
        if person["departure"] and person["appointment"]:
            event_type = "both"
        elif person["departure"]:
            event_type = "departure"
        else:
            event_type = "appointment"
        events.append({"event_type": event_type,
                       "person_name": person["person_name"],
                       "title": person["title"],
                       "effective_date": person["effective_date"]})
    return events


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def main():
    cutoff_iso = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    print(f"Looking for Item {TARGET_ITEM} 8-Ks filed on or after {cutoff_iso}\n")
    rows = []
    for company in COMPANIES:
        ticker, cik = company["ticker"], company["cik"]
        try:
            filings = recent_502_filings(cik, cutoff_iso)
        except Exception as exc:
            print(f"WARNING: {ticker}: could not query EDGAR submissions API ({exc}). "
                  f"Moving on to the next company.")
            continue

        if not filings:
            print(f"{ticker}: No executive events in past 12 months")
            continue

        company_events = 0
        for filing in filings:
            if not filing["primary_doc"]:
                print(f"  WARNING: {ticker} {filing['accession']}: no primary document "
                      f"listed. Skipping this filing.")
                continue
            url = filing_doc_url(cik, filing)
            try:
                text = html_to_text(sec_get(url).text)
            except Exception as exc:
                print(f"  WARNING: {ticker} {filing['accession']}: could not download "
                      f"{url} ({exc}). Skipping this filing.")
                continue

            events = extract_events(text)
            if not events:
                print(f"  NOTE: {ticker} | {filing['filing_date']} | Item 5.02 filing with "
                      f"no departure/appointment found (often a 5.02(e) compensation-only "
                      f"filing): {url}")
                continue

            for event in events:
                row = {"company": company["company"], "ticker": ticker, "cik": cik,
                       "filing_date": filing["filing_date"], **event}
                row = {k: (v if (v is not None and str(v).strip()) else NOT_FOUND)
                       for k, v in row.items()}
                rows.append(row)
                company_events += 1
                print(f"{ticker} | {row['filing_date']} | {row['event_type']} | "
                      f"{row['person_name']} | {row['title']}")

        if company_events == 0:
            print(f"{ticker}: {len(filings)} Item 5.02 filing(s) in the past 12 months, "
                  f"but none reported a departure or appointment")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} events to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
