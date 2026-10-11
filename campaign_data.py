"""CSV validation and shared calculations for every dashboard view."""
from io import BytesIO
import csv
import math
import pandas as pd

PLATFORMS = ["Facebook", "Instagram", "Pinterest", "Twitter"]
REQUIRED = ["campaign_id", "campaign_name", "platform", "spend", "clicks", "conversions", "revenue"]
DIMENSIONS = ["platform", "audience", "campaign_goal"]
MEASURES = ["spend", "clicks", "conversions", "revenue"]


def load_csv(content):
    """Return normalized data and notices. Never silently discard bad records."""
    notices = []
    try:
        header = next(csv.reader(content.decode("utf-8-sig").splitlines()))
        normalized = [v.strip().lower().replace(" ", "_") for v in header]
        if len(normalized) != len(set(normalized)):
            raise ValueError("CSV contains duplicate column names.")
        df = pd.read_csv(BytesIO(content), encoding="utf-8-sig", dtype=str)
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError, StopIteration) as exc:
        raise ValueError("Upload a valid UTF-8 CSV with a header and campaign records.") from exc
    df.columns = normalized
    missing = [col for col in REQUIRED if col not in df]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    if df.empty:
        raise ValueError("This CSV has no campaign records.")
    for col in ["campaign_id", "campaign_name", "platform"]:
        df[col] = df[col].fillna("").str.strip()
        if df[col].eq("").any():
            raise ValueError(f"{col} must be present on every row.")
    aliases = {p.lower(): p for p in PLATFORMS}
    aliases.update({"x": "Twitter", "twitter/x": "Twitter"})
    df["platform"] = df["platform"].str.lower().map(aliases)
    if df["platform"].isna().any():
        raise ValueError("Channels must be Facebook, Instagram, Pinterest, or Twitter (X).")
    for col in MEASURES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any() or not df[col].map(math.isfinite).all() or df[col].lt(0).any():
            raise ValueError(f"{col} must contain finite, nonnegative numbers on every row.")
    for col in ["clicks", "conversions"]:
        if df[col].mod(1).ne(0).any():
            raise ValueError(f"{col} must contain whole numbers.")
        df[col] = df[col].astype("int64")
    for col in ["audience", "campaign_goal"]:
        if col not in df:
            df[col] = "Unspecified"
            notices.append(f"No {col.replace('_', ' ')} column: these records are labeled Unspecified.")
        else:
            df[col] = df[col].fillna("").str.strip().replace("", "Unspecified")
    if "currency" not in df:
        df["currency"] = "USD"
        notices.append("No currency column: monetary values are assumed to be USD.")
    df["currency"] = df["currency"].fillna("").str.strip().str.upper()
    if df["currency"].str.fullmatch(r"[A-Z]{3}").ne(True).any():
        raise ValueError("Use a three-letter currency code on every row, such as USD.")
    if df["currency"].nunique() != 1:
        raise ValueError("Use one currency per CSV. Convert amounts before combining currencies.")
    date_col = "date" if "date" in df else "end_date" if "end_date" in df else None
    if date_col is None:
        raise ValueError("Include date (YYYY-MM-DD), or end_date for reporting-period totals.")
    dates = pd.to_datetime(df[date_col], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise ValueError(f"{date_col} must contain valid YYYY-MM-DD dates on every row.")
    df["date"] = dates.dt.normalize()
    if date_col == "end_date":
        notices.append("Reporting-period totals are plotted and filtered by end_date; no daily values are inferred.")
    if "start_date" in df:
        starts = pd.to_datetime(df["start_date"], format="%Y-%m-%d", errors="coerce")
        if starts.isna().any() or (starts > df["date"]).any():
            raise ValueError("start_date must be valid and on or before the reporting date.")
    if df["conversions"].gt(df["clicks"]).any():
        notices.append("Some records have more conversions than clicks. Check your attribution definition.")
    df = derived(df)
    notices.append("ROI is recalculated from revenue and ad spend; other business costs are excluded.")
    return df, notices


def derived(frame):
    frame = frame.copy()
    frame["profit"] = frame["revenue"] - frame["spend"]
    frame["roi_percent"] = frame["profit"].div(frame["spend"].where(frame["spend"].ne(0))) * 100
    frame["conversion_rate_percent"] = frame["conversions"].div(frame["clicks"].where(frame["clicks"].ne(0))) * 100
    frame["cpc"] = frame["spend"].div(frame["clicks"].where(frame["clicks"].ne(0)))
    frame["cpa"] = frame["spend"].div(frame["conversions"].where(frame["conversions"].ne(0)))
    return frame


def filter_data(df, start, end, channels, audiences, goals):
    mask = df["date"].between(pd.Timestamp(start), pd.Timestamp(end))
    for column, chosen in zip(DIMENSIONS, [channels, audiences, goals]):
        mask &= df[column].isin(chosen)
    return df.loc[mask].copy()


def aggregate(df, by):
    return derived(df.groupby(by, dropna=False, as_index=False)[MEASURES].sum())


def totals(df):
    return derived(pd.DataFrame([df[MEASURES].sum()])).iloc[0]


def time_series(df, frequency):
    buckets = {"Daily": "D", "Weekly": "W-SUN", "Monthly": "M"}
    result = df.copy()
    result["period"] = result["date"].dt.to_period(buckets[frequency]).dt.start_time
    return aggregate(result, ["period", "platform"]).sort_values("period")

