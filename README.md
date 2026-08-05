# Chipotle (CMG) Nowcasting Dashboard

A dashboard tracking Chipotle's quarterly revenue growth ahead of earnings releases, combining alternative data (web scraping) and macro data (APIs).

**Live:** https://dashboardchipotle-vn6f9jxaflmjqxmzfdbc5s.streamlit.app/

---

## Indicators

**Revenue Y/Y & Food Cost Y/Y (SEC)**
Chipotle's Food & Beverage Revenue and Food/Beverage/Packaging Cost, pulled from 8-K earnings exhibits and XBRL company facts (XBRL fills in pre-2018 history, where 8-K text isn't reliably regex-parseable). Growth computed as year-over-year change.

**US Retail Sales: Food Services Y/Y — FRED `RSFSDP`**
Monthly retail sales for the US food-service sector, aggregated to quarterly (sum) and expressed Y/Y. Used as a sector-demand benchmark: comparing it to Chipotle's own revenue Y/Y helps separate market-wide tailwinds from company-specific share gains. Partial current quarters are handled via a quarter-to-date (QTD) comparison against the same partial period a year earlier.

**PPI Meats Y/Y — FRED `WPU0221`**
Producer Price Index for processed meats, aggregated to quarterly (mean), Y/Y. Proxy for input-cost pressure on Chipotle's food costs. 

**Google Trends**
Weekly search interest for 4 Chipotle-related queries in the US (`chipotle`, `chipotle delivery`, `chipotle menu`, `chipotle near me`), smoothed with a 3-week rolling average.

**Open restaurants**
Restaurant count scraped from Chipotle's official store-locator site across FR, CA, DE, UK, US. Open/closed status is inferred by comparing each day's scraped URLs against the previous snapshot.

**Active job postings**
Postings scraped from jobs.chipotle.com, classified into categories (crew/kitchen ops, management, IT & data, real estate, etc.) via keyword rules.

---

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_dashboard.py
```

Producer scripts (SEC, FRED, scrapers) need a `.env` with a SEC-compliant email and a FRED API key.
