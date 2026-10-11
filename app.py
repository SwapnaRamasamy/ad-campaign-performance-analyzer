from pathlib import Path
import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from campaign_data import load_csv, filter_data, aggregate, totals, time_series, PLATFORMS

st.set_page_config(page_title="Campaign Compass", page_icon="📊", layout="wide")
COLORS = {"Facebook": "#2563eb", "Instagram": "#db2777", "Pinterest": "#dc2626", "Twitter": "#0f766e"}
VIEWS = ["Overview", "Platform Comparison", "Campaign Details", "Time Series"]
st.markdown("""
<style>
.block-container {padding-top:2rem; padding-bottom:3rem}
[data-testid="stMetric"] {background:#f1f5f9; border:1px solid #e2e8f0; border-radius:12px; padding:16px}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {color:#0f172a}
</style>
""", unsafe_allow_html=True)
st.title("Campaign Compass")
st.caption("See where your advertising budget turns into results.")

with st.sidebar:
    st.header("Campaign data")
    upload = st.file_uploader("Upload campaign CSV", type=["csv"])
    sample = Path(__file__).with_name("sample_campaign_performance.csv")
    if upload is None:
        if not sample.exists():
            st.info("Upload a campaign CSV to get started.")
            st.stop()
        content = sample.read_bytes()
        st.caption("Using the fictional sample dataset.")
        st.download_button("Download sample CSV", content, file_name=sample.name, mime="text/csv")
    else:
        content = upload.getvalue()
        st.caption(f"Loaded: {upload.name}")
try:
    data, notices = load_csv(content)
except ValueError as exc:
    st.error(f"Could not load campaign data: {exc}")
    st.stop()

signature = hashlib.sha256(content).hexdigest()
if st.session_state.get("data_signature") != signature:
    for key in ["dates", "channels", "audiences", "goals", "search"]:
        st.session_state.pop(key, None)
    st.session_state["data_signature"] = signature

minimum, maximum = data["date"].min().date(), data["date"].max().date()
channels_all = [p for p in PLATFORMS if p in data["platform"].unique()]
audiences_all = sorted(data["audience"].unique())
goals_all = sorted(data["campaign_goal"].unique())

def reset_filters():
    st.session_state["dates"] = (minimum, maximum)
    st.session_state["channels"] = channels_all
    st.session_state["audiences"] = audiences_all
    st.session_state["goals"] = goals_all

with st.sidebar:
    st.header("Global filters")
    st.caption("These filters apply to all four views. Clearing a selection returns no records.")
    dates = st.date_input("Reporting date range", value=(minimum, maximum), key="dates", format="YYYY-MM-DD")
    channels = st.multiselect("Channel", channels_all, default=channels_all, key="channels")
    audiences = st.multiselect("Audience", audiences_all, default=audiences_all, key="audiences")
    goals = st.multiselect("Campaign goal", goals_all, default=goals_all, key="goals")
    st.button("Reset filters", on_click=reset_filters, width="stretch")
    st.divider()
    st.caption("ROI = (revenue − ad spend) ÷ ad spend × 100. Undefined rates appear as N/A.")

with st.expander("Data notes and CSV format"):
    for notice in notices:
        st.write("• " + notice)
    st.write("Required: campaign_id, campaign_name, platform, spend, clicks, conversions, revenue, and date or end_date.")
    st.write("Optional: audience, campaign_goal, currency, start_date. Use one row per campaign, channel, audience, goal, and reporting period; avoid overlapping totals.")
    st.write("Conversions are your chosen completed actions. Use the same definition across channels.")

def keep_view_selected():
    selected = st.session_state.get("view")
    if selected is None:
        st.session_state["view"] = st.session_state["active_view"]
    else:
        st.session_state["active_view"] = selected


st.session_state.setdefault("active_view", st.session_state.get("view") or VIEWS[0])
view = st.segmented_control(
    "View", VIEWS, selection_mode="single", default=VIEWS[0],
    key="view", on_change=keep_view_selected, width="stretch",
)
if len(dates) != 2:
    st.info("Choose both a start and end date to show results.")
    st.stop()
filtered = filter_data(data, dates[0], dates[1], channels, audiences, goals)
if filtered.empty:
    st.info("No campaigns match these filters. Widen the date range, select channels, audiences or goals, or reset filters.")
    st.stop()

currency = data["currency"].iloc[0]
money = lambda value: f"{currency} {value:,.2f}" if pd.notna(value) else "N/A"
percent = lambda value: f"{value:,.1f}%" if pd.notna(value) else "N/A"
summary = totals(filtered)
st.caption(f"{len(filtered):,} reporting records · {filtered['campaign_id'].nunique():,} campaigns · {dates[0]} to {dates[1]} · Currency: {currency}")
cols = st.columns(5)
for column, label, value in zip(cols,
    [f"Ad spend ({currency})", "Clicks (count)", "Conversions (count)", f"Revenue ({currency})", "ROI (%)"],
    [money(summary["spend"]), f"{summary['clicks']:,.0f}", f"{summary['conversions']:,.0f}", money(summary["revenue"]), percent(summary["roi_percent"])]):
    column.metric(label, value)

def chart(fig):
    fig.update_layout(template="plotly_white", margin=dict(l=16, r=16, t=45, b=16))
    st.plotly_chart(fig, use_container_width=True)

def table(frame):
    labels = {
        "platform": "Channel", "campaign_id": "Campaign ID", "campaign_name": "Campaign",
        "audience": "Audience", "campaign_goal": "Goal", "spend": f"Spend ({currency})",
        "revenue": f"Revenue ({currency})", "profit": f"Return above ad spend ({currency})",
        "clicks": "Clicks (count)", "conversions": "Conversions (count)", "roi_percent": "ROI (%)",
        "conversion_rate_percent": "Conversion rate (%)", "cpc": f"Cost per click ({currency})",
        "cpa": f"Cost per conversion ({currency})",
    }
    shown = frame.rename(columns=labels)
    configs = {}
    for col in ["spend", "revenue", "profit", "cpc", "cpa", "roi_percent", "conversion_rate_percent"]:
        if labels[col] in shown:
            configs[labels[col]] = st.column_config.NumberColumn(format="%.2f")
    for col in ["clicks", "conversions"]:
        if labels[col] in shown:
            configs[labels[col]] = st.column_config.NumberColumn(format="%d")
    st.dataframe(shown, hide_index=True, width="stretch", column_config=configs)

def spend_conversions(frame, x, title):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=frame[x], y=frame["spend"], name=f"Spend ({currency})", marker_color="#2563eb",
                         hovertemplate=f"%{{x}}<br>Spend: {currency} %{{y:,.2f}}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=frame[x], y=frame["conversions"], name="Conversions (count)",
                            mode="lines+markers", line=dict(color="#0f766e", width=3),
                            hovertemplate="%{x}<br>Conversions: %{y:,.0f}<extra></extra>"), secondary_y=True)
    fig.update_layout(title=title, legend_title_text="Metric", hovermode="x unified")
    fig.update_yaxes(title_text=f"Spend ({currency})", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Conversions (count)", secondary_y=True, rangemode="tozero")
    return fig

if view == "Overview":
    st.subheader("Spend and results at a glance")
    frequency = st.selectbox("Trend interval", ["Monthly", "Weekly", "Daily"], key="overview_interval")
    series = time_series(filtered, frequency)
    overall = aggregate(series, ["period"])
    chart(spend_conversions(overall, "period", "Spend versus conversions"))
    left, right = st.columns(2)
    platforms = aggregate(filtered, ["platform"])
    with left:
        chart(px.pie(platforms, values="spend", names="platform", hole=0.65,
                     color="platform", color_discrete_map=COLORS, title=f"Budget by channel ({currency})"))
    with right:
        chart(px.bar(platforms, x="platform", y="conversions", color="platform",
                     color_discrete_map=COLORS, title="Conversions by channel",
                     labels={"platform": "Channel", "conversions": "Conversions (count)"}))
    finite = platforms.dropna(subset=["roi_percent"]).sort_values("roi_percent", ascending=False)
    if not finite.empty:
        best = finite.iloc[0]
        st.info(f"Highest ROI in this selection: {best['platform']} at {percent(best['roi_percent'])}, with {best['conversions']:,.0f} conversions and {money(best['spend'])} spent.")
    st.caption("ROI uses total revenue and spend. Channel comparisons reflect the selected data and attribution definitions.")

elif view == "Platform Comparison":
    st.subheader("Compare advertising channels")
    platforms = aggregate(filtered, ["platform"])
    left, right = st.columns(2)
    with left:
        chart(spend_conversions(platforms, "platform", "Channel spend versus conversions"))
    with right:
        fig = px.bar(platforms, x="platform", y="roi_percent", color="platform",
                     color_discrete_map=COLORS, title="Return on ad spend investment",
                     labels={"platform": "Channel", "roi_percent": "ROI (%)"})
        fig.add_hline(y=0, line_color="#64748b")
        chart(fig)
    table(platforms)
    st.caption("ROI and conversion rates are calculated from channel totals, rather than averaged across campaigns. N/A means the denominator is zero.")

elif view == "Campaign Details":
    st.subheader("Find and compare campaigns")
    search = st.text_input("Search campaign name or ID", placeholder="e.g. Summer or FB001", key="search")
    campaigns = aggregate(filtered, ["campaign_id", "campaign_name", "platform", "audience", "campaign_goal"])
    if search.strip():
        campaigns = campaigns.loc[
            campaigns["campaign_name"].str.contains(search.strip(), case=False, regex=False) |
            campaigns["campaign_id"].str.contains(search.strip(), case=False, regex=False)]
    if campaigns.empty:
        st.info("No campaigns match your search. Try another name or campaign ID.")
    else:
        st.caption(f"{len(campaigns):,} campaign groups. Click a column header to sort. Search affects this table and its export.")
        campaigns = campaigns.sort_values("roi_percent", ascending=False, na_position="last")
        table(campaigns)
        st.download_button("Export campaign results", campaigns.to_csv(index=False).encode("utf-8"),
                           "filtered_campaign_results.csv", "text/csv")

elif view == "Time Series":
    st.subheader("Explore performance over time")
    left, right = st.columns(2)
    with left:
        metric = st.selectbox("Metric", ["Spend", "Clicks", "Conversions", "Revenue", "ROI", "Conversion rate", "Cost per conversion"])
    with right:
        frequency = st.selectbox("Time interval", ["Monthly", "Weekly", "Daily"])
    series = time_series(filtered, frequency)
    mapping = {
        "Spend": ("spend", f"Spend ({currency})"), "Clicks": ("clicks", "Clicks (count)"),
        "Conversions": ("conversions", "Conversions (count)"), "Revenue": ("revenue", f"Revenue ({currency})"),
        "ROI": ("roi_percent", "ROI (%)"), "Conversion rate": ("conversion_rate_percent", "Conversion rate (%)"),
        "Cost per conversion": ("cpa", f"Cost per conversion ({currency})")}
    field, label = mapping[metric]
    if series[field].notna().any():
        fig = px.line(series, x="period", y=field, color="platform", markers=True,
                      color_discrete_map=COLORS, labels={"period": "Reporting bucket start", field: label, "platform": "Channel"})
        fig.update_layout(hovermode="x unified")
        chart(fig)
    else:
        st.info("This metric is undefined for the selected records because its denominator is zero.")
    st.caption("Only reported periods are plotted; gaps are not treated as zero. Period totals use their end date before grouping into buckets.")
    table(series.rename(columns={"period": "Reporting bucket start"}))


