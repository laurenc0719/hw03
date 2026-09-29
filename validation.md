### 5A — Known-Answer Check: Earnings

I checked Apple's fourth quarter FY25 8k.

| Check | Official Source | Your CSV | Match? |
|---|---|---|
| Apple Q4 FY2025 Revenue | $102.5 billion (Apple press release, Oct 30, 2025: "The Company posted quarterly revenue of $102.5 billion") | 102.5 billion | Yes |
| Apple Q4 FY2025 EPS Diluted | $1.85 (Apple press release, Oct 30, 2025: "Diluted earnings per share was $1.85") | 1.85 | Yes |

Both values matched an Apple Newsroom report exactly, so no there was no fix for this check.

### 5B — Known-Answer Check: Executive Events

I checked NVIDIA appointing Nicholas Parker as EVP from the 8-K filed 2026-07-02.

| Check | News Source Confirms? | Notes |
|---|---|---|
| Person name and title | Yes | CSV: Nicholas Parker, "Executive Vice President, Worldwide Field Operations." TradingView (July 2, 2026) and TipRanks both report Parker was named NVIDIA's Executive Vice President, Worldwide Field Operations. |
| Event type (departure/appointment) | Yes | CSV: appointment. Both sources describe Parker as the incoming successor to Ajay K. Puri, a 21-year NVIDIA veteran retiring from the role; the same filing produced a separate departure row for Puri. |
| Effective date | Yes | CSV: 2026-08-24. TradingView and TipRanks both report an effective date of August 24, 2026. |

### 5C — Cross-Validation: Earnings via Yahoo Finance

I checked Apple's fourth quarter FY25 8k.

| Metric | From 8-K text extraction | From yfinance | Match? |
|---|---|---|---|
| Revenue | 102.5 billion | $102,466,000,000 | Yes |
| Net Income | 27,466 million | $27,466,000,000 | Yes |

I figure the difference in my text scraping vs. the yfinance is that the press release headline rounds revenue to $102.5 billion, while yfinance reports the exact figure of $102,466 million, which rounds to the same amount.

### 5D — Pipeline Integrity Checks

| Check | Expected | Actual | Pass/Fail |
|---|---|---|
| `earnings_history.csv` row count | Up to 20 (5 companies × 4 quarters) | 20 | Pass |
| `executive_events.csv` row count | At least 0 | 24 | Pass |
| `corporate_events_timeline.csv` created | Yes | Yes (24 rows, one per executive event) | Pass |
| Rows with all three fields `"NOT_FOUND"` | 0  | 0 | Pass |
