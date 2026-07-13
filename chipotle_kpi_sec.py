# -*- coding: utf-8 -*-

import requests
import re
import html
import time
import pandas as pd
from dotenv import load_dotenv
import os
from config import BASE_DIR

load_dotenv(dotenv_path=BASE_DIR / ".env.txt")
load_dotenv()

mail = os.getenv("mail")
CIK = "1058090"
CIK_PADDED = CIK.zfill(10)
HEADERS = {'User-Agent': mail}  
START_DATE = "2010-01-01"

LABEL_VARIANTS = {
    'Opened': [
        'Opened',
        'Number of restaurants opened',
        'New restaurant openings',
        'Company-operated restaurants opened',
    ],
    'Permanent Closures': [
        'Permanent closures',
        'Restaurant closures',
        'Chipotle permanent closures',
    ],
    'Relocations': [
        'Relocations',
        'Restaurant relocations',
        'Chipotle relocations',
    ],
    'Total Restaurants (Press Release)': [
        'Total',
        'Number of restaurants at end of period',
        'Company-operated restaurants at end of period',
    ],
    'Average Restaurant Sales ($000)': [
        r'Average restaurant sales(?:\(\d+\))?',
    ],
    'Comparable Restaurant Sales %': [
        r'Comparable restaurant sales increase/\(decrease\)',
        r'Comparable restaurant sales increase\s*\(decrease\)',
        'Comparable restaurant sales increase',
        'Comparable restaurant sales decrease',
    ]
}

def get_all_filings(cik_padded):
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def get_8k_accessions(submissions, start_date=START_DATE):
    recent = submissions['filings']['recent']
    df = pd.DataFrame({
        'form': recent['form'], 'accessionNumber': recent['accessionNumber'],
        'filingDate': recent['filingDate'], 'primaryDocument': recent['primaryDocument'],
    })
    df = df[df['form'] == '8-K']
    df = df[df['filingDate'] >= start_date]
    return df.reset_index(drop=True)


def get_filing_documents(cik_padded, accession_number):
    accession_nodash = accession_number.replace('-', '')
    index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik_padded)}/{accession_nodash}/"
    r = requests.get(index_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    docs = re.findall(r'href="([^"]+\.htm)"', r.text)
    return [index_url + d.split('/')[-1] if not d.startswith('http') else d for d in docs]


def find_earnings_exhibit(doc_urls):
    return [d for d in doc_urls if re.search(r'ex.?99|pressrelease|earnings', d, re.IGNORECASE)]


def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    text = html.unescape(r.text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def parse_supplemental_table(text):
    match = re.search(
        r'(?:company-owned\s+)?restaurant unit data.*?(?=partner-operated restaurant unit data|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if match:
        block = match.group(0)[:3000]
    else:
        idx = text.lower().find('number of restaurants opened')
        if idx == -1:
            idx = text.lower().find('opened')
        if idx == -1:
            return None
        block = text[max(0, idx - 50):idx + 3000]

    value_pattern = r'(?:\(?-?\$?\s*[\d,]+\.?\d*\s?%?\)?|-)'

    def extract_row(label_variants, n_values_range=(3, 6)):
        for label in label_variants:
            for n in range(n_values_range[1], n_values_range[0] - 1, -1):
                m = re.search(rf'{label}\s*((?:\s*{value_pattern}\s*){{{n}}})', block, re.IGNORECASE)
                if m:
                    raw = m.group(1)
                    nums = re.findall(value_pattern, raw)
                    cleaned = []
                    for x in nums[:n]:
                        if x.strip() == '-':
                            cleaned.append(0.0)
                            continue
                        neg = x.strip().startswith('(')
                        x_clean = re.sub(r'[\(\)\$,%\s]', '', x)
                        try:
                            val = float(x_clean)
                            cleaned.append(-val if neg else val)
                        except ValueError:
                            cleaned.append(None)
                    return cleaned
        return None

    result = {metric: extract_row(variants) for metric, variants in LABEL_VARIANTS.items()}
    if all(v is None for v in result.values()):
        return None
    return result

def filing_date_to_quarter(filing_date):
    d = pd.Timestamp(filing_date)
    if d.month in [1, 2, 3]:
        return d.year - 1, 4
    elif d.month in [4, 5, 6]:
        return d.year, 1
    elif d.month in [7, 8, 9]:
        return d.year, 2
    else:
        return d.year, 3


def step_back_quarter(year, quarter, n):
    total = year * 4 + (quarter - 1) - n
    return total // 4, total % 4 + 1


def scrape_all_earnings_releases(max_filings=None, delay=0.3):
    submissions = get_all_filings(CIK_PADDED)
    df_8k = get_8k_accessions(submissions)
    print(f"[INFO] {len(df_8k)} filings 8-K trouvés depuis {START_DATE}")

    if max_filings:
        df_8k = df_8k.head(max_filings)

    rows = []
    failed_no_exhibit = 0
    failed_no_table = []

    for _, row in df_8k.iterrows():
        try:
            doc_urls = get_filing_documents(CIK_PADDED, row['accessionNumber'])
            exhibits = find_earnings_exhibit(doc_urls)
            if not exhibits:
                failed_no_exhibit += 1
                continue

            text = fetch_text(exhibits[0])
            parsed = parse_supplemental_table(text)
            if parsed is None:
                failed_no_table.append((row['filingDate'], exhibits[0]))
                continue

            year0, q0 = filing_date_to_quarter(row['filingDate'])
            for metric, values in parsed.items():
                if values is None:
                    continue
                for i, val in enumerate(values):
                    if val is None or i >= 5:
                        continue
                    y_i, q_i = step_back_quarter(year0, q0, i)
                    quarter_label = f'Q{q_i} {y_i}'
                    rows.append({'metric': metric, 'quarter_label': quarter_label,
                                  'value': val, 'filed': row['filingDate']})
        except:
            continue

        time.sleep(delay)

    return pd.DataFrame(rows), failed_no_table

INCOME_STATEMENT_LABELS = {
    'Food and Beverage Revenue': r'Food and beverage revenue',
    'Food, Beverage and Packaging Cost': r'Food,?\s*beverage and packaging',
    'Labor': r'\bLabor\b',
    'Occupancy': r'\bOccupancy\b',
    'Other Operating Costs': r'Other operating costs',
    'G&A Expenses': r'General and administrative expenses',
}


def parse_income_statement(text, labels=INCOME_STATEMENT_LABELS, window_size=300):

    number_pattern = r'\$?\s*[\d,]+\.?\d*'

    def extract_two_dollar_values(label_pattern, n_tokens=4):
        for m_label in re.finditer(label_pattern, text, re.IGNORECASE):
            start = m_label.end()
            window = text[start:start + window_size]
            m_vals = re.match(rf'\s*((?:\s*{number_pattern}\s*%?\s*){{{n_tokens}}})', window)
            if not m_vals:
                continue
            tokens = re.findall(number_pattern, m_vals.group(1))
            if len(tokens) < 3:
                continue
            def clean(t):
                try:
                    return float(re.sub(r'[\$,\s]', '', t))
                except ValueError:
                    return None
            val1, val2 = clean(tokens[0]), clean(tokens[2])
            if val1 is not None and val2 is not None:
                return val1, val2
        return None, None

    result = {}
    for metric, label_pattern in labels.items():
        current, prior = extract_two_dollar_values(label_pattern)
        result[metric] = (current, prior)

    if all(v == (None, None) for v in result.values()):
        return None
    return result


def scrape_income_statement_history(max_filings=None, delay=0.3):

    submissions = get_all_filings(CIK_PADDED)
    df_8k = get_8k_accessions(submissions)

    if max_filings:
        df_8k = df_8k.head(max_filings)

    rows = []
    for _, row in df_8k.iterrows():
        try:
            doc_urls = get_filing_documents(CIK_PADDED, row['accessionNumber'])
            exhibits = find_earnings_exhibit(doc_urls)
            if not exhibits:
                continue

            text = fetch_text(exhibits[0])
            parsed = parse_income_statement(text)
            if parsed is None:
                continue

            year0, q0 = filing_date_to_quarter(row['filingDate'])
            current_label = f"Q{q0} {year0}"
            prior_label = f"Q{q0} {year0 - 1}"

            for metric, (current_val, prior_val) in parsed.items():
                if current_val is not None:
                    rows.append({'metric': metric, 'quarter_label': current_label,
                                  'value': current_val, 'filed': row['filingDate']})
                if prior_val is not None:
                    rows.append({'metric': metric, 'quarter_label': prior_label,
                                  'value': prior_val, 'filed': row['filingDate']})

        except :
            continue

        time.sleep(delay)

    return pd.DataFrame(rows)

def fetch_company_facts(cik_padded=CIK_PADDED):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def flatten_company_facts(data):
    rows = []
    for taxonomy in data.get('facts', {}):
        for tag_name, tag_data in data['facts'][taxonomy].items():
            label = tag_data.get('label', tag_name)
            for unit, values in tag_data.get('units', {}).items():
                for entry in values:
                    rows.append({
                        'tag': tag_name, 'label': label,
                        'start': entry.get('start'), 'end': entry.get('end'),
                        'value': entry.get('val'), 'fiscal_year': entry.get('fy'),
                        'fiscal_period': entry.get('fp'), 'form': entry.get('form'),
                        'filed': entry.get('filed'),
                    })
    df = pd.DataFrame(rows)
    for col in ['start', 'end', 'filed']:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

XBRL_PRE_2018_TAGS = {
    'FoodAndBeverageRevenue': 'Food and Beverage Revenue',
    'FoodAndBeverageCostOfSales': 'Food, Beverage and Packaging Cost',
}

def build_xbrl_pre2018_rows(df_all, tags=XBRL_PRE_2018_TAGS, cutoff_year=2018):

    df = df_all[df_all['tag'].isin(tags.keys())].copy()
    df['duration_days'] = (df['end'] - df['start']).dt.days

    q_flow = df[(df['form'] == '10-Q') & df['duration_days'].between(80, 100)].copy()
    fy_flow = df[(df['form'] == '10-K') & df['duration_days'].between(350, 380)].copy()

    q_flow['q_num'] = q_flow['end'].dt.quarter
    q_flow['q_year'] = q_flow['end'].dt.year

    rows = []
    for tag, metric_name in tags.items():
        tag_q = q_flow[q_flow['tag'] == tag]
        tag_fy = fy_flow[fy_flow['tag'] == tag]

        for _, r in tag_q.iterrows():
            if r['q_year'] < cutoff_year:
                rows.append({'metric': metric_name, 'quarter_label': f"Q{r['q_num']} {r['q_year']}",
                              'value': r['value'], 'filed': r['filed']})

        for _, fy_row in tag_fy.iterrows():
            fy_year_real = fy_row['end'].year
            if fy_year_real >= cutoff_year:
                continue
            q123 = tag_q[(tag_q['q_year'] == fy_year_real) & (tag_q['q_num'].isin([1, 2, 3]))]
            if q123['q_num'].nunique() < 3:
                continue
            q123_sum = q123.groupby('q_num')['value'].first().sum()
            q4_value = fy_row['value'] - q123_sum
            rows.append({'metric': metric_name, 'quarter_label': f"Q4 {fy_year_real}",
                          'value': q4_value, 'filed': fy_row['filed']})

    return pd.DataFrame(rows)


def quarter_label_sort_key(label):
    q, y = label.split(' ')
    return int(y), int(q[1])


def build_full_pivot(earnings_rows, income_rows, xbrl_rows):

    all_rows = pd.concat([earnings_rows, income_rows, xbrl_rows], ignore_index=True)
    all_rows['filed'] = pd.to_datetime(all_rows['filed'])
    all_rows = all_rows.sort_values('filed').drop_duplicates(subset=['metric', 'quarter_label'], keep='last')

    pivot = all_rows.pivot_table(index='quarter_label', columns='metric', values='value', aggfunc='first')

    order = all_rows[['quarter_label']].drop_duplicates().copy()
    order['sort_key'] = order['quarter_label'].apply(quarter_label_sort_key)
    order = order.sort_values('sort_key')
    pivot = pivot.reindex(order['quarter_label'])

    return pivot

# %%

if __name__ == "__main__":

    earnings_rows, failed_no_table = scrape_all_earnings_releases()

    income_rows = scrape_income_statement_history()

    xbrl_data = fetch_company_facts()
    df_all_xbrl = flatten_company_facts(xbrl_data)
    xbrl_rows = build_xbrl_pre2018_rows(df_all_xbrl)

    pivot_full = build_full_pivot(earnings_rows, income_rows, xbrl_rows)
    pivot_full.to_excel(BASE_DIR / "chipotle_sec_key_metrics.xlsx")
