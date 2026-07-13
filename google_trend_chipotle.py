# -*- coding: utf-8 -*-
"""
Created on Thu Jul  9 17:02:25 2026
@author: Mathis
"""
# -*- coding: utf-8 -*-

import pandas as pd
import time
from pytrends.request import TrendReq
from config import BASE_DIR

GEO = 'US'  
TIMEFRAME = 'today 5-y'  
KEYWORDS = [
    'chipotle near me',
    'chipotle menu',
    'chipotle delivery',
    'chipotle'
]

SMOOTH_WINDOW = 3  

def fetch_trends(keywords, geo=GEO, timeframe=TIMEFRAME, retries=3, delay=5):
 
    pytrends = TrendReq(
    hl='en-US',
    tz=360,
    requests_args={'headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}}
)
    all_data = []
    for kw in keywords:
        for attempt in range(retries):
            try:
                pytrends.build_payload([kw], timeframe=timeframe, geo=geo)
                df = pytrends.interest_over_time()
                if df.empty:
                    break
                df = df.reset_index()[['date', kw]]
                df.columns = ['date', 'interest']
                df['keyword'] = kw
                all_data.append(df)
                break
            except Exception as e:
                time.sleep(delay * (attempt + 1))
        else:
            continue
        time.sleep(delay)
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


def build_wide_pivot(df_long):
    return df_long.pivot_table(index='date', columns='keyword', values='interest')


def smooth_weekly(df_wide, window=SMOOTH_WINDOW):

    return df_wide.rolling(window=window, min_periods=1).mean()



# %%
if __name__ == "__main__":
    df_long = fetch_trends(KEYWORDS)
    df_wide = build_wide_pivot(df_long)

    df_smooth = smooth_weekly(df_wide)
    df_smooth.to_excel(BASE_DIR / "google_trend_weekly_chipotle_smoothed.xlsx")
