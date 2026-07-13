# -*- coding: utf-8 -*-
"""
Scraper des offres d'emploi Chipotle (jobs.chipotle.com).
Site server-rendu -> requests + BeautifulSoup, pas besoin de Selenium.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os
import glob
import datetime
import undetected_chromedriver as uc
from config import BASE_DIR

Historic_DIR = os.path.join(BASE_DIR, "Historic_collection")
Current_DIR     = os.path.join(BASE_DIR, "Current_collection")
NUMBER_DIR     = os.path.join(BASE_DIR, "Number")

TODAY   = datetime.datetime.now().strftime('%Y%m%d')

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

BASE_URL = "https://jobs.chipotle.com"

def get_driver(Historic_DIR):
    os.makedirs(Historic_DIR, exist_ok=True)
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1400,900")
    options.add_argument("--lang=fr-FR")
    options.add_argument("--no-sandbox")
    return uc.Chrome(options=options)

def get_total_pages(soup):
    results_section = soup.find(id="search-results")
    if results_section and results_section.get("data-total-pages"):
        return int(results_section["data-total-pages"])
    return None

def parse_jobs_page(soup):
    jobs = []
    results_section = soup.find(id="search-results-list")
    if not results_section:
        return jobs

    for a in results_section.find_all("a", href=re.compile(r"^/job/")):
        title_tag = a.find("h2")
        location_tag = a.find("span", class_="job-location")
        address_tag = a.find("span", class_="job-address")

        jobs.append({
            "title": title_tag.get_text(strip=True) if title_tag else None,
            "location": location_tag.get_text(strip=True) if location_tag else None,
            "address": address_tag.get_text(strip=True) if address_tag else None,
            "job_id": a.get("data-job-id"),
            "url": BASE_URL + a["href"],
            "date_importation": TODAY
        })
    return jobs


def scrape_all_jobs(max_pages=None, delay=1.0):
    
    all_jobs = []

    r = requests.get(f"{BASE_URL}/search-jobs", headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    total_pages = get_total_pages(soup)

    jobs = parse_jobs_page(soup)
    all_jobs += jobs

    n_pages_to_fetch = total_pages if max_pages is None else min(max_pages, total_pages)

    for page in range(2, n_pages_to_fetch + 1):
        time.sleep(delay)
        url = f"{BASE_URL}/search-jobs?p={page}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        jobs = parse_jobs_page(soup)
        if not jobs:
            break

        all_jobs += jobs

    return pd.DataFrame(all_jobs)



CATEGORY_KEYWORDS = {
    "Restaurant Ops (Crew/Kitchen)": [
        r"crew member", r"kitchen leader", r"kitchen keader", r"service leader",
        r"^crew\b", r"apprentice.*general manager", r"hourly general manager"
    ],
    "Restaurant Management": [
        r"general manager", r"assistant general manager", r"assistant manager",
        r"^ca, general manager"
    ],
    "Facilities & Field Equipment": [
        r"facilities (specialist|manager)", r"field equipment technician",
        r"field technician", r"equipment technician"
    ],
    "Food Safety & Quality": [
        r"food safety", r"quality engineering", r"health and food safety"
    ],
    "Procurement & Supply Chain": [
        r"procurement", r"supply chain", r"outbound logistics", r"demand planning",
        r"purchasing"
    ],
    "Finance & Analytics": [
        r"analyst", r"unemployment compliance", r"sales and supply chain finance",
        r"business intelligence"
    ],
    "IT & Data": [
        r"it restaurant", r"database administrator", r"data platform engineer",
        r"platform engineering", r"corporate applications", r"product owner",
        r"product manager"
    ],
    "HR & Recruiting": [
        r"hr business partner", r"recruiter", r"learning & development"
    ],
    "Marketing & Brand": [
        r"brand activation", r"brand insights", r"brand marketing", r"loyalty, crm",
        r"customer care"
    ],
    "Real Estate & Construction": [
        r"lease administrator", r"administrator, property", r"design & construction",
        r"development strategy"
    ],
    "Field Leadership (District Mgmt)": [
        r"field leader"
    ],
    "Executive / Senior Leadership": [
        r"vice president", r"senior director", r"director,"
    ],
}

def categorize(title):
    title_lower = title.lower()
    for category, patterns in CATEGORY_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, title_lower):
                return category
    return "Uncategorized"


# %%


if __name__ == "__main__":
    df = scrape_all_jobs(max_pages=None)
    df.to_excel(os.path.join(Historic_DIR, f"{TODAY}_Chipotle.xlsx"), index=False)
    
    files = glob.glob(f"{Historic_DIR}/*_Chipotle.xlsx")
    
    data = pd.concat([pd.read_excel(f) for f in files], ignore_index=True)
    seen_dates = data.groupby('job_id')['date_importation'].agg(first_seen='min', last_seen='max')

    data = data.drop_duplicates(subset="job_id", keep="last")
    data = data.merge(seen_dates, on="job_id")
    
    data['job_category'] = data['title'].apply(categorize)
    data.to_excel(f"{BASE_DIR}/Chipotle_jobs_all.xlsx", index=False)