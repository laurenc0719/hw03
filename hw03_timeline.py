"""
hw03_timeline.py
Joins earnings_history.csv and executive_events.csv into a corporate events timeline.

For every executive event, finds the nearest earnings filing for the SAME company and adds:
  - days_to_nearest_earnings : absolute days between the two filing dates
  - event_timing             : 'before earnings' | 'after earnings' | 'same week' (<= 7 days)

Output: corporate_events_timeline.csv (same folder as this script)
Run:    python hw03/hw03_timeline.py   (works from any working directory)
"""
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
EARNINGS_CSV = HERE / "earnings_history.csv"
EVENTS_CSV = HERE / "executive_events.csv"
OUTPUT_CSV = HERE / "corporate_events_timeline.csv"
SAME_WEEK_DAYS = 7


def classify(signed_days: int) -> str:
    """signed_days = event date minus nearest earnings date (negative = event came first)."""
    if abs(signed_days) <= SAME_WEEK_DAYS:
        return "same week"
    return "before earnings" if signed_days < 0 else "after earnings"


def main() -> None:
    earnings = pd.read_csv(EARNINGS_CSV, dtype={"cik": str})
    events = pd.read_csv(EVENTS_CSV, dtype={"cik": str})
    earnings["filing_date"] = pd.to_datetime(earnings["filing_date"])
    events["filing_date"] = pd.to_datetime(events["filing_date"])

    if events.empty:
        print("No executive events found - nothing to join.")
        return

    # Prefix earnings columns so the shared names (company, ticker, cik, filing_date) don't collide
    earnings_renamed = earnings.add_prefix("earnings_")

    rows = []
    for _, ev in events.iterrows():
        pool = earnings_renamed[earnings_renamed["earnings_ticker"] == ev["ticker"]].copy()
        if pool.empty:
            rows.append({**ev.to_dict(), "days_to_nearest_earnings": pd.NA, "event_timing": pd.NA})
            continue
        pool["signed"] = (ev["filing_date"] - pool["earnings_filing_date"]).dt.days
        # nearest by absolute distance; on an exact tie, take the earlier earnings date
        best = pool.assign(absd=pool["signed"].abs()).sort_values(["absd", "earnings_filing_date"]).iloc[0]
        rows.append({
            **ev.to_dict(),
            **best.drop(labels=["signed", "absd"]).to_dict(),
            "days_to_nearest_earnings": int(best["absd"]),
            "event_timing": classify(int(best["signed"])),
        })

    timeline = pd.DataFrame(rows)
    timeline["filing_date"] = timeline["filing_date"].dt.strftime("%Y-%m-%d")
    timeline["earnings_filing_date"] = pd.to_datetime(timeline["earnings_filing_date"]).dt.strftime("%Y-%m-%d")
    timeline = timeline.sort_values(["company", "filing_date"], ascending=[True, False]).reset_index(drop=True)
    timeline.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(timeline)} rows to {OUTPUT_CSV.name}\n")

    # ---- Per-company summary ----
    print("=" * 78)
    print("EXECUTIVE EVENTS vs. NEAREST EARNINGS ANNOUNCEMENT")
    print("=" * 78)
    for company, grp in timeline.groupby("company", sort=False):
        print(f"\n{company} ({grp['ticker'].iloc[0]}) - {len(grp)} event(s)")
        for _, r in grp.iterrows():
            print(f"  {r['filing_date']}  {r['event_type']:<11} {str(r['person_name'])[:26]:<26} "
                  f"-> {r['event_timing']:<15} "
                  f"({r['days_to_nearest_earnings']}d vs. earnings on {r['earnings_filing_date']})")
    all_companies = set(earnings["company"])
    for missing in sorted(all_companies - set(timeline["company"])):
        print(f"\n{missing} - no executive events")

    # ---- Final counts ----
    counts = timeline["event_timing"].value_counts()
    print("\n" + "=" * 78)
    print("FINAL COUNT (all companies)")
    print("=" * 78)
    print(f"  Before earnings : {counts.get('before earnings', 0)}")
    print(f"  After earnings  : {counts.get('after earnings', 0)}")
    print(f"  Same week       : {counts.get('same week', 0)}  (within {SAME_WEEK_DAYS} days - counted in neither bucket above)")
    print(f"  Total events    : {len(timeline)}")


if __name__ == "__main__":
    main()
