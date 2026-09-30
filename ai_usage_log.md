1. Specifications A+B (I didn't read ahead and did it all in one prompt rather than two, my bad)

### Specification A — Earnings Pipeline (Item 2.02)

you are a 530,000 IQ harvard grad who is an expert business intelligence analyst and has extensive experience in finance and understands SEC filings inside and out. I need a python script that fufills the following requirements completely and without exception:

```markdown
1. Sets the SEC EDGAR `User-Agent` header to `"MIS3060 Villanova lcurley@villanova.edu"` on all HTTP requests
2. For each of the five companies, queries the EDGAR submissions API at `https://data.sec.gov/submissions/CIK{cik}.json` and filters for 8-K filings where the `items` field contains `"2.02"` (Results of Operations)
3. Selects the most recent **four** such filings per company (one per quarter)
4. For each filing, constructs the filing index URL, identifies the earnings press release exhibit (`.htm` file), downloads it, and strips HTML to plain text
5. Extracts from the plain text: quarterly revenue (as a number in millions or billions), diluted EPS, net income, and the reporting period (e.g., "fourth quarter fiscal 2024")
6. Prints the extracted row for each filing as it is processed, in the format: `[Ticker] | [Period] | Revenue: $X | EPS: $X | Net Income: $X`
7. Saves all rows to `hw03/earnings_history.csv` with columns: `company`, `ticker`, `cik`, `filing_date`, `period`, `revenue_reported`, `eps_diluted`, `net_income`
8. Where a field cannot be extracted (regex returns no match), stores the string `"NOT_FOUND"` rather than leaving the cell blank — blank cells and missing data are two different things

### Specification B — Executive Events Pipeline (Item 5.02)

Your specification for `hw03/hw03_executives.py` must describe a script that:

1. Sets the same EDGAR `User-Agent` header on all requests
2. For each of the five companies, queries the EDGAR submissions API and filters for 8-K filings where the `items` field contains `"5.02"` (Departure of Directors or Officers) and the `filingDate` is within the past 12 months
3. For each matching filing, downloads the full 8-K text, strips HTML, and extracts: event type (`"departure"` or `"appointment"` or `"both"`), the person's full name, their title, and the effective date of the change
4. If a filing reports multiple events (e.g., one departure and one appointment), creates a separate row for each event
5. Prints each extracted event as it is processed: `[Ticker] | [Date] | [Event Type] | [Name] | [Title]`
6. If no Item 5.02 filings are found for a company in the past 12 months, prints `[Ticker]: No executive events in past 12 months` — this is valid data, not an error
7. Saves all events to `hw03/executive_events.csv` with columns: `company`, `ticker`, `cik`, `filing_date`, `event_type`, `person_name`, `title`, `effective_date`

---

```


```markdown
You will extract data for these five companies. Their CIK numbers are required to query EDGAR — do not look them up, use the values below exactly.

| Company | Ticker | SEC CIK |
|---|---|---|
| Apple Inc. | AAPL | 0000320193 |
| Microsoft Corporation | MSFT | 0000789019 |
| NVIDIA Corporation | NVDA | 0001045810 |
| JPMorgan Chase & Co. | JPM | 0000019617 |
| Walmart Inc. | WMT | 0000104169 |
```

be sure your output script fulfills all of the following requirements. read every specification i gave you and the five companies completely. also i am checking this over with chatgpt afterwords so be sure to not mess up.

## Which companies' extractions required iteration

The earnings pipeline extracted revenue, diluted EPS, net income, and the reporting period for all 20 filings on the first run, with no "NOT_FOUND" values, so none of the revenue or EPS regex patterns needed follow-up fixes. 

However, validation surfaced one earnings issue with Walmart: all four Walmart rows showed net income in "billion" (e.g., "6,366 billion"), which is impossible because it would exceed Walmart's annual revenue. The number was correct but the unit label was wrong, because the script took its unit from the first "in millions/billions" phrase in the press release, and Walmart's release says "in billions" before its "(Amounts in millions...)" statement header. I had the script updated to prioritize "in millions," then reran it, and Walmart's net income now correctly reads in millions.

The executive events pipeline needed iteration for NVIDIA and Walmart. The name extraction mistook two capitalized phrases for people, producing an "Achievement Target" row from an NVIDIA compensation filing and a "Transition Date" row from a Walmart filing. I had claude update the script to add those words to its list of words that can never be part of a person's name. Several real events also came back with a title of "NOT_FOUND" (for example, Walmart's C. Douglas McMillon and John R. Furner and JPMorgan's Marianne Lake), because those filings describe the role in phrasing the title patterns don't cover. I also had claude fix these instances.

## One thing the generated script did that I would not have thought to specify

The earnings script automatically skipped non-GAAP and alternative figures. It ignores any number labeled "adjusted," "non-GAAP," or "managed," as well as full-year totals, so it only captures the GAAP, as-reported, quarterly figure. I would not have thought to specify this, because my specification only asked for "quarterly revenue" and "diluted EPS," but press releases often report several versions of the same metric side by side. This behavior was correct and did not need adjustment. For example, JPMorgan reports both "reported revenue" and "managed revenue" for the third quarter of 2025 ($46.4 billion vs. $47.1 billion), and my CSV correctly captured the reported $46.4 billion. Similarly, Walmart's third quarter fiscal 2026 release lists both GAAP EPS of $0.77 and adjusted EPS of $0.62, and the script correctly stored the GAAP $0.77. Without this rule, the pipeline could have silently mixed GAAP and non-GAAP numbers across companies, which would have made the quarter-to-quarter comparisons unreliable.

