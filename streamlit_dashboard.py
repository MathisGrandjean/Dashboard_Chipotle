# -*- coding: utf-8 -*-

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from config import BASE_DIR

DATA_DIR = BASE_DIR / "data"

PATHS = {
    "sec":         DATA_DIR /"chipotle_sec_key_metrics.xlsx",
    "trends":      DATA_DIR /"google_trend_weekly_chipotle_smoothed.xlsx",
    "fred":        DATA_DIR /"fred_api_data.xlsx",
    "restaurants": DATA_DIR / "data_restaurants.xlsx",
    "jobs":        DATA_DIR /"Chipotle_jobs_all.xlsx",
}

COL_RSFSDP = "Advance Retail Sales Food Services yy"
COL_PPI = "Producer Price Index Meats yy"


C_ORANGE = "#E8590C"
C_GREEN  = "#7CB342"
C_GOLD   = "#F2A65A"
C_BLUE   = "#5B8DEF"
TREND_COLORS = [C_ORANGE, C_GREEN, C_GOLD, C_BLUE]

def style_fig(fig, height=400, pct_yaxis=False):
    """Unified styling for all charts."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(26,29,36,0.45)",
        font=dict(family="Segoe UI, Arial", size=13, color="#FAFAFA"),
        margin=dict(t=15, b=10, l=10, r=10),
        height=height,
        legend=dict(orientation="h", y=-0.28, title=None,
                    font=dict(size=12, color="#C9CDD6")),
        xaxis=dict(showgrid=False, tickfont=dict(size=11)),
        yaxis=dict(gridcolor="rgba(139,146,165,0.15)", zerolinecolor="rgba(139,146,165,0.3)"),
        hovermode="x unified",
    )
    if pct_yaxis:
        fig.update_yaxes(tickformat=".0%")
    return fig

st.set_page_config(page_title="Chipotle Nowcasting", layout="wide")


st.markdown("""
<style>
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    [data-testid="stHeader"] {
        background-color: #0E1117;
    }
    h1, h2, p, span, label {
        color: #FAFAFA;
    }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1A1D24 0%, #22262F 100%);
        border: 1px solid rgba(232,89,12,0.3);
        border-radius: 14px;
        padding: 20px 22px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3);
    }
    [data-testid="stMetricValue"] { color: #E8590C; font-weight: 700; }
    [data-testid="stMetricLabel"] { color: #C9CDD6; }
    h3 {
        color: #F2A65A !important;
        font-size: 1.02rem !important;
        font-weight: 600 !important;
        border-left: 4px solid #E8590C;
        padding-left: 10px;
    }
    hr { border-color: rgba(139,146,165,0.15) !important; }
    [data-testid="stDataFrame"] {
        background-color: #1A1D24;
        border-radius: 10px;
    }
    [data-testid="stCaptionContainer"] { color: #8B92A5; }
    [data-testid="stTooltipContent"] {
        background-color: #333333 !important;
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_all():
    sec = pd.read_excel(PATHS["sec"])
    trends = pd.read_excel(PATHS["trends"])
    fred = pd.read_excel(PATHS["fred"])
    restaurants = pd.read_excel(PATHS["restaurants"])
    jobs = pd.read_excel(PATHS["jobs"])
    return sec, trends, fred, restaurants, jobs

sec, trends, fred, restaurants, jobs = load_all()

def normalize_units(series, threshold=10_000_000):
    """SEC file mixes dollars and thousands of dollars across years."""
    return series.where(series <= threshold, series / 1000)

def quarter_sort_key(q_label):
    """'Q3 2012' -> Period('2012Q3') for chronological sorting."""
    q, y = q_label.split(" ")
    return pd.Period(f"{y}{q}")

sec["_sort"] = sec["quarter_label"].apply(quarter_sort_key)
sec = sec.sort_values("_sort").reset_index(drop=True)

sec["revenue_k"] = normalize_units(sec["Food and Beverage Revenue"])
sec["food_cost_k"] = normalize_units(sec["Food, Beverage and Packaging Cost"])

sec["revenue_yy"] = sec["revenue_k"].pct_change(4)
sec["food_cost_yy"] = sec["food_cost_k"].pct_change(4)

fred["_sort"] = fred["quarter"].apply(quarter_sort_key)
fred = fred.sort_values("_sort")

macro = fred.merge(
    sec[["quarter_label", "revenue_yy", "food_cost_yy"]],
    left_on="quarter", right_on="quarter_label", how="left"
).sort_values("_sort")

macro_plot = macro[macro["_sort"] >= pd.Period("2020Q3")]


n_restaurants_open = (restaurants["status"].str.lower() == "open").sum()
last_rest_scrape = pd.to_datetime(
    restaurants["last_confirmed_open_date"].max(), format="%Y%m%d"
).strftime("%b %d, %Y")

last_scrape_raw = jobs["last_seen"].max()
last_jobs_scrape = pd.to_datetime(str(last_scrape_raw), format="%Y%m%d").strftime("%b %d, %Y")
jobs_active = jobs[jobs["last_seen"] == last_scrape_raw]
jobs_by_cat = jobs_active["job_category"].value_counts()
n_nro = jobs_active["title"].str.contains("New Restaurant Opening", case=False, na=False).sum()

last_trends_date = pd.to_datetime(trends["date"].max()).strftime("%b %d, %Y")
last_fred_quarter = macro_plot["quarter"].iloc[-1]
last_sec_quarter = sec.dropna(subset=["revenue_yy"])["quarter_label"].iloc[-1]

last_sec_restaurants = (
    sec["Total Restaurants"].dropna().iloc[-1]
    if "Total Restaurants" in sec.columns and sec["Total Restaurants"].notna().any()
    else None
)

st.title("Chipotle Nowcasting Dashboard")
st.caption(
    "Tracking Chipotle (CMG) quarterly revenue growth ahead of earnings, using alternative data "
    "(restaurant locations, job postings, Google Trends) and macro indicators (FRED retail sales, commodity prices)."
)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Open restaurants (live)",
          f"{n_restaurants_open:,}",
          help=f"Scraped from locations.chipotle.com — last update: {last_rest_scrape}")
k2.metric("Total restaurants (SEC)",
          f"{last_sec_restaurants:,.0f}" if last_sec_restaurants is not None else "n/a",
          help=f"From SEC quarterly filings — latest quarter: {last_sec_quarter}")
k3.metric("Active job postings",
          f"{len(jobs_active):,}",
          help=f"Scraped from jobs.chipotle.com — last update: {last_jobs_scrape}")
last_rev = macro["revenue_yy"].dropna().iloc[-1] if macro["revenue_yy"].notna().any() else None
k4.metric("Latest Revenue Y/Y (SEC)",
          f"{last_rev:.1%}" if last_rev is not None else "n/a",
          help=f"From SEC quarterly filings — latest quarter: {last_sec_quarter}")

st.caption(
    f"Google Trends: {last_trends_date} · FRED macro: {last_fred_quarter} · SEC filings: {last_sec_quarter}"
)

st.divider()

c1, c2 = st.columns(2)

with c1:
    st.subheader("Sector demand vs Chipotle revenue — US Advance Retail Sales: Food Services and Drinking Places y/y (FRED: RSFSDP) vs CMG Food & Beverage revenue y/y (SEC filings)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=macro_plot["quarter"], y=macro_plot[COL_RSFSDP],
        name="US Advance Retail Sales: Food Services and Drinking Places y/y (FRED)",
        line=dict(color=C_ORANGE, width=3)
    ))
    fig1.add_trace(go.Scatter(
        x=macro_plot["quarter"], y=macro_plot["revenue_yy"],
        name="Chipotle F&B Revenue y/y (SEC)",
        line=dict(color=C_GREEN, width=3)
    ))
    st.plotly_chart(style_fig(fig1, height=420, pct_yaxis=True), use_container_width=True)

with c2:
    st.subheader("Input cost pressure — Producer Price Index: Meats y/y (FRED: WPU0221)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=macro_plot["quarter"], y=macro_plot[COL_PPI],
        name="PPI: Processed Foods & Feeds: Meats y/y",
        line=dict(color=C_ORANGE, width=3),
        fill="tozeroy", fillcolor="rgba(232,89,12,0.08)"
    ))
    st.plotly_chart(style_fig(fig2, height=420, pct_yaxis=True), use_container_width=True)

st.divider()


c3, c4 = st.columns(2)

with c3:
    st.subheader(f"Consumer search interest — Google Trends, weekly, 3-week smoothed (through {last_trends_date})")
    trend_cols = ["chipotle", "chipotle delivery", "chipotle menu", "chipotle near me"]
    fig3 = px.line(trends, x="date", y=trend_cols,
                   color_discrete_sequence=TREND_COLORS)
    fig3.update_traces(line_width=2)
    fig3 = style_fig(fig3)
    fig3.update_layout(xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig3, use_container_width=True)

with c4:
    st.subheader(f"Hiring activity by category — jobs.chipotle.com (scraped {last_jobs_scrape})")
    fig4 = px.bar(
        jobs_by_cat.sort_values(),
        orientation="h",
        labels={"value": "", "index": ""},
        text_auto=True,
    )
    fig4.update_traces(
        marker=dict(color=C_ORANGE, opacity=0.85),
        textfont=dict(size=11, color="#FAFAFA"),
        showlegend=False
    )
    fig4 = style_fig(fig4)
    fig4.update_layout(showlegend=False,
                       xaxis=dict(showgrid=False, showticklabels=False))
    st.plotly_chart(fig4, use_container_width=True)

st.divider()


st.subheader("Quarterly indicators summary — FRED macro series vs Chipotle SEC-reported figures")

table = macro_plot[["_sort", "quarter", COL_RSFSDP, COL_PPI, "revenue_yy", "food_cost_yy"]].copy()
table = table.sort_values("_sort", ascending=False).drop(columns="_sort")
table.columns = ["Quarter", "US Retail Sales Food Services y/y (FRED)", "PPI Meats y/y (FRED)",
                 "CMG Revenue y/y (SEC)", "CMG Food Cost y/y (SEC)"]
for col in table.columns[1:]:
    table[col] = table[col].map(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
st.dataframe(table, use_container_width=True, hide_index=True)

st.caption(
    "Sources: FRED — Federal Reserve Economic Data (RSFSDP, WPU0221) · SEC quarterly filings (10-Q/10-K) · "
    "jobs.chipotle.com (own scraper) · locations.chipotle.com (own scraper) · Google Trends"
)
