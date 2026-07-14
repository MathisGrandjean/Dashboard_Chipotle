# -*- coding: utf-8 -*-
"""
Created on Sun Jul 12 10:20:11 2026
@author: Mathis
"""
import requests
import pandas as pd
from dotenv import load_dotenv
import os
from config import BASE_DIR

load_dotenv(dotenv_path=BASE_DIR / ".env.txt")
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")


FRIENDLY_NAMES = {
    "RSFSDP": "Advance Retail Sales Food Services yy",
    "WPU0221": "Producer Price Index Meats yy",
}


def get_fred_series(series_id, api_key):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json"
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()["observations"]
    df = pd.DataFrame(data)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.rename(columns={"value": series_id})


def process_fred_series(df, series_id, agg_method="sum"):
    df = df.sort_values("date").set_index("date")
    df["quarter"] = df.index.to_period("Q")
    df["month_in_q"] = df.index.month - (df["quarter"].dt.quarter - 1) * 3
    n_months_per_q = df.groupby("quarter")["month_in_q"].count()
    complete_quarters = n_months_per_q[n_months_per_q == 3].index
    last_q = df["quarter"].max()
    n_months_available = df[df["quarter"] == last_q]["month_in_q"].max()
    is_last_q_partial = n_months_available < 3
    df_complete = df[df["quarter"].isin(complete_quarters)]
    if agg_method == "sum":
        full_q = df_complete.groupby("quarter")[series_id].sum()
    else:
        full_q = df_complete.groupby("quarter")[series_id].mean()
    result = full_q.to_frame()
    result[f"{series_id}_yy"] = result[series_id].pct_change(4)
    result["is_qtd"] = False
    if is_last_q_partial:
        df_qtd = df[df["month_in_q"] <= n_months_available]
        if agg_method == "sum":
            qtd_series = df_qtd.groupby("quarter")[series_id].sum()
        else:
            qtd_series = df_qtd.groupby("quarter")[series_id].mean()
        val_current = qtd_series.get(last_q)
        val_prior_year = qtd_series.get(last_q - 4)
        if val_current is not None and val_prior_year is not None and val_prior_year != 0:
            yy_qtd = (val_current / val_prior_year) - 1
            result.loc[last_q, series_id] = val_current
            result.loc[last_q, f"{series_id}_yy"] = yy_qtd
            result.loc[last_q, "is_qtd"] = True
    return result


rsfsdp = get_fred_series("RSFSDP", FRED_API_KEY)
ppi_meats = get_fred_series("WPU0221", FRED_API_KEY)

rsfsdp_q = process_fred_series(rsfsdp, "RSFSDP", agg_method="sum")
ppi_meats_q = process_fred_series(ppi_meats, "WPU0221", agg_method="mean")

df = pd.concat(
    [rsfsdp_q[["RSFSDP_yy"]], ppi_meats_q[["WPU0221_yy"]]],
    axis=1
)

df = df.sort_index()

df.index = df.index.astype(str).str.replace(r"(\d{4})Q(\d)", r"Q\2 \1", regex=True)
df.index.name = "quarter"

df_final = df.dropna(subset=["RSFSDP_yy", "WPU0221_yy"]).reset_index()

df_final = df_final.rename(columns={
    "RSFSDP_yy": FRIENDLY_NAMES["RSFSDP"],
    "WPU0221_yy": FRIENDLY_NAMES["WPU0221"],
})

df_final.to_excel(BASE_DIR / "fred_api_data.xlsx", index=False)
