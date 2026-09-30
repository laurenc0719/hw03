#!/usr/bin/env python3
"""
hw03_yfinance_check.py
MIS3060 HW3, Part 5C: Cross-validate 8-K extracted earnings against yfinance.

Pulls Apple's quarterly revenue and net income from Yahoo Finance (yfinance)
for the SAME quarter checked in 5A (fiscal Q4 2025, quarter ended
2025-09-27), compares them to the values the 8-K pipeline wrote to
earnings_history.csv, and prints a Markdown table ready to paste into
validation.md. It also prints the most recent quarter yfinance has, for
reference, since that is what "most recent quarterly revenue" would return.

Run (venv active, inside hw03):   python hw03_yfinance_check.py
Requires:                         pip install yfinance pandas
"""

import csv
import re
from pathlib import Path

import pandas as pd
import yfinance as yf

TICKER = "AAPL"
PERIOD_LABEL = "fourth quarter fiscal 2025"   # period string in earnings_history.csv
QUARTER_END = "2025-09-27"                     # Apple's fiscal Q4 2025 quarter-end date
EARNINGS_CSV = Path(__file__).resolve().parent / "earnings_history.csv"

UNIT_MULTIPLIER = {"thousand": 1e3, "million": 1e6, "billion": 1e9}


def parse_reported(value):
    """'102.5 billion' -> (102500000000.0, 50000000.0): dollars and rounding tolerance
    (half of the last digit the press release reported)."""
    m = re.match(r"\s*([\d,]+(?:\.(\d+))?)\s+(thousand|million|billion)", str(value), re.I)
    if not m:
        return None, None
    multiplier = UNIT_MULTIPLIER[m.group(3).lower()]
    decimals = len(m.group(2) or "")
    number = float(m.group(1).replace(",", ""))
    return number * multiplier, 0.5 * (10 ** -decimals) * multiplier


def fmt_dollars(x):
    return f"${x / 1e9:,.3f} billion" if x is not None and not pd.isna(x) else "NOT_AVAILABLE"


def pick_row(frame, names):
    for name in names:
        if name in frame.index:
            return frame.loc[name]
    return None


def main():
    # --- 8-K pipeline values from earnings_history.csv -------------------------
    with open(EARNINGS_CSV, newline="", encoding="utf-8") as f:
        row = next((r for r in csv.DictReader(f)
                    if r["ticker"] == TICKER and r["period"] == PERIOD_LABEL), None)
    if row is None:
        raise SystemExit(f"No {TICKER} row with period '{PERIOD_LABEL}' in {EARNINGS_CSV}")

    # --- yfinance values ---------------------------------------------------------
    stmt = yf.Ticker(TICKER).quarterly_income_stmt
    if stmt is None or stmt.empty:
        raise SystemExit("yfinance returned no quarterly income statement - try again later.")
    stmt.columns = pd.to_datetime(stmt.columns)
    revenue_row = pick_row(stmt, ["Total Revenue", "Operating Revenue"])
    income_row = pick_row(stmt, ["Net Income", "Net Income Common Stockholders"])

    print(f"yfinance quarters available for {TICKER}: "
          + ", ".join(c.strftime("%Y-%m-%d") for c in stmt.columns))
    latest = stmt.columns.max()
    print(f"Most recent quarter in yfinance ({latest:%Y-%m-%d}): "
          f"revenue {fmt_dollars(revenue_row[latest])}, "
          f"net income {fmt_dollars(income_row[latest])}\n")

    # Yahoo labels quarters by calendar month-end (2025-09-30) while Apple's fiscal
    # quarter actually ended 2025-09-27, so match the closest column within 10 days.
    fiscal_end = pd.Timestamp(QUARTER_END)
    gaps = {col: abs((col - fiscal_end).days) for col in stmt.columns}
    target = min(gaps, key=gaps.get)
    if gaps[target] > 10:
        print(f"WARNING: yfinance has no quarter ending near {QUARTER_END}. It only keeps the "
              f"last ~5 quarters, so this quarter may have rolled off. Pick a newer quarter.")
        return
    if target != fiscal_end:
        print(f"NOTE: yfinance labels this quarter {target:%Y-%m-%d}; Apple's fiscal quarter "
              f"actually ended {QUARTER_END}. Same quarter, different date label.\n")

    checks = [
        ("Revenue", row["revenue_reported"], revenue_row[target]),
        ("Net Income", row["net_income"], income_row[target]),
    ]

    print(f"{TICKER} fiscal Q4 2025 (quarter ended {QUARTER_END}), 8-K filed {row['filing_date']}\n")
    print("| Metric | From 8-K text extraction | From yfinance | Match? |")
    print("|---|---|---|---|")
    for metric, reported, yf_value in checks:
        dollars, tolerance = parse_reported(reported)
        if dollars is None or pd.isna(yf_value):
            match = "Cannot compare"
        else:
            diff = abs(dollars - float(yf_value))
            match = "Yes" if diff <= tolerance else f"No (off by {fmt_dollars(diff)})"
        yf_text = "NOT_AVAILABLE" if pd.isna(yf_value) else f"${float(yf_value):,.0f}"
        print(f"| {metric} | {reported} | {yf_text} | {match} |")


if __name__ == "__main__":
    main()
