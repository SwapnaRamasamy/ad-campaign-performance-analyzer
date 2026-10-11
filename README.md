# Campaign Compass

A Streamlit dashboard for comparing Facebook, Instagram, Pinterest, and Twitter campaigns.

## Features

- Overview with key metrics and spend-versus-conversions trends.
- Platform Comparison with channel totals, ROI, and cost metrics.
- Campaign Details with campaign name/ID search and CSV export.
- Time Series with daily, weekly, and monthly reporting buckets.
- Segmented view navigation and shared date, channel, audience, and goal filters.
- CSV validation, metric units, and clear messages for empty selections.

## Clone from GitHub

```powershell
git clone https://github.com/SwapnaRamasamy/ad-campaign-performance-analyzer.git
cd ad-campaign-performance-analyzer
```

Follow the local setup below. Includes fictional CSV and XLSX samples, the app in
`app.py`, shared calculations in `campaign_data.py`, and tests in `tests/`.


## Run locally (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501. The bundled fictional CSV loads automatically; upload your own CSV in the sidebar.

## Replit

Import these files into a Python Repl, install requirements with `pip install -r requirements.txt`, and run:
`streamlit run app.py --server.address 0.0.0.0 --server.port 8501`.
Use the Replit web preview. Python 3.11 or newer is recommended for a new deployment.

## Data contract

Required columns: campaign_id, campaign_name, platform, spend, clicks, conversions, revenue, and either date or end_date.
Optional: audience, campaign_goal, currency, start_date. Existing roi_percent is recalculated.

Dates use YYYY-MM-DD. Use one record per campaign/channel/audience/goal/reporting period.
Monthly aggregate rows are assigned to end_date; filtering includes the complete row when that reporting date is selected. It does not prorate monthly totals or infer daily activity.
Daily input should use date. Avoid duplicate or overlapping totals, because each row is counted once.
Missing audience/goal values are shown as Unspecified. The original sample does not contain those dimensions; add them to your uploads to compare segments.
X is accepted as an alias for Twitter. Currency defaults to USD when absent; mixed currencies are rejected.
Negative, nonfinite, missing numeric values and invalid dates are rejected with an actionable message.

## Views and calculations

All four views consume the same date/channel/audience/goal filtered dataset and share summary metrics.
Campaign search only refines the campaign table and download. Clearing a global multi-select produces no results; Reset filters restores all values.
Spend and revenue show the currency code. Clicks and conversions are counts. ROI and conversion rate show percent.
ROI = (total revenue - total spend) / total spend * 100.
Conversion rate = total conversions / total clicks * 100.
CPC = total spend / total clicks; CPA = total spend / total conversions.
These ratios use aggregated totals, not averages of row ratios. A zero denominator displays N/A.
ROI excludes costs other than ad spend. Use consistent conversion and attribution definitions across channels.
Uploads stay in the running app session; the app does not write uploaded CSVs to disk.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Includes data validation, weighted metrics, filter combinations, time buckets, and Streamlit view/filter/search checks.
