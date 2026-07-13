# -*- coding: utf-8 -*-
"""
Created on Mon Jul 13 09:24:05 2026

@author: Mathis
"""

import os
import re
import glob
import time
import random
import datetime
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

from config import BASE_DIR

Historic_DIR = os.path.join(BASE_DIR, "Historic_collection")
Current_DIR     = os.path.join(BASE_DIR, "Current_collection")
NUMBER_DIR     = os.path.join(BASE_DIR, "Number")

TODAY   = datetime.datetime.now().strftime('%Y%m%d')
NA = "N/A"  

COUNTRIES = {
    "France":    {"suffix": ".fr",    "has_state": False},
    "Canada":    {"suffix": ".ca",    "has_state": True},
    "Allemagne": {"suffix": ".de",    "has_state": False},
    "UK":        {"suffix": ".co.uk", "has_state": False},
    "US":        {"suffix": ".com",   "has_state": True},
}

BASE_URL = "https://locations.chipotle"

RESTAURANT_COLS = ["date", "country", "state_name", "city_name",
                    "restaurant_information", "restaurant_url", "gmaps_url", "import_date"]
NUMBER_COLS  = ["level", "country", "state_name", "city_name", "count"]
STATE_COLS = ["restaurant_url", "country", "state_name", "city_name",
              "restaurant_information", "gmaps_url",
              "first_seen_date", "last_confirmed_open_date", "status", "closed_date"]

def get_driver(Historic_DIR):
    os.makedirs(Historic_DIR, exist_ok=True)
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1400,900")
    options.add_argument("--lang=fr-FR")
    options.add_argument("--no-sandbox")
    return uc.Chrome(options=options)

def accept_cookies(driver):
    try:
        driver.find_element(By.XPATH, '//*[@id="ketch-banner-button-secondary"]').click()
    except Exception:
        pass

def parse_count(a_tag):
    raw = a_tag.get_attribute("data-count")
    if not raw:
        return None
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None

def extract_links(driver):
    items = []
    for el in driver.find_elements(By.XPATH, '//li[@class="mb-4"]'):
        try:
            link = el.find_element(By.XPATH, ".//a")
            items.append({"name": el.text, "url": link.get_attribute("href"), "count": parse_count(link)})
        except Exception:
            continue
    return items

def load_latest_number(NUMBER_DIR: str):
    files = glob.glob(os.path.join(NUMBER_DIR, "*.xlsx"))
    if not files:
        return {}, {}, pd.DataFrame(columns=NUMBER_COLS)

    number_df = pd.read_excel(max(files, key=os.path.getmtime))
    number_df["state_name"] = number_df["state_name"].fillna(NA)
    number_df["city_name"] = number_df["city_name"].fillna(NA)

    state_counts, city_counts = {}, {}
    for _, row in number_df.iterrows():
        if row["level"] == "state":
            state_counts[(row["country"], row["state_name"])] = row["count"]
        else:
            city_counts[(row["country"], row["state_name"], row["city_name"])] = row["count"]

    return state_counts, city_counts, number_df[NUMBER_COLS]

def merge_number(previous_number_df, new_rows):
    new_df = pd.DataFrame(new_rows, columns=NUMBER_COLS)
    new_df["city_name"] = new_df["city_name"].fillna(NA)
    combined = pd.concat([previous_number_df, new_df], ignore_index=True)
    return combined.drop_duplicates(subset=["level", "country", "state_name", "city_name"], keep="last")[NUMBER_COLS]

def scrape_restaurants():
    driver = get_driver(Historic_DIR)
    state_counts, city_counts, previous_number_df = load_latest_number(NUMBER_DIR)

    rows, number_rows = [], []

    try:
        for country_name, conf in COUNTRIES.items():
            driver.get(BASE_URL + conf["suffix"])
            time.sleep(3)
            accept_cookies(driver)
            time.sleep(1)

            states = extract_links(driver) if conf["has_state"] else [{"name": NA, "url": None, "count": None}]

            for state in states:
                state_name, state_url, state_count = state["name"], state["url"], state["count"]

                if conf["has_state"]:
                    number_rows.append({"level": "state", "country": country_name,
                                       "state_name": state_name, "city_name": NA, "count": state_count})
                    if state_count is not None and state_counts.get((country_name, state_name)) == state_count:
                        continue
                    driver.get(state_url)
                    cities = extract_links(driver)
                else:
                    cities = extract_links(driver)

                for city in cities:
                    city_name, city_url, city_count = city["name"], city["url"], city["count"]

                    number_rows.append({"level": "city", "country": country_name,
                                       "state_name": state_name, "city_name": city_name, "count": city_count})
                    if city_count is not None and city_counts.get((country_name, state_name, city_name)) == city_count:
                        continue

                    driver.get(city_url)
                    time.sleep(random.uniform(1, 5))

                    restaurants = []
                    for r in driver.find_elements(By.XPATH, '//li[@class="w-full md:w-1/2 lg:w-1/4"]'):
                        try:
                            restaurants.append({"name": r.text, "url": r.find_element(By.XPATH, ".//a").get_attribute("href")})
                        except Exception:
                            continue

                    for restaurant in restaurants:
                        try:
                            driver.get(restaurant["url"])
                            time.sleep(random.uniform(1, 5))
                            try:
                                gmaps_url = driver.find_element(By.XPATH, '//a[contains(@href,"google")]').get_attribute("href")
                            except Exception:
                                gmaps_url = None

                            rows.append({
                                "date": TODAY, "country": country_name, "state_name": state_name,
                                "city_name": city_name, "restaurant_information": restaurant["name"],
                                "restaurant_url": restaurant["url"], "gmaps_url": gmaps_url,
                                "import_date": datetime.datetime.now()
                            })
                        except Exception:
                            continue
    finally:
        driver.quit()

    return pd.DataFrame(rows, columns=RESTAURANT_COLS), number_rows, previous_number_df


def update_open_closed_status(day_df, master_df):
    if master_df is None or master_df.empty:
        master_df = pd.DataFrame(columns=STATE_COLS)
    if day_df.empty:
        return master_df

    new_rows = []
    for country, state_name, city_name in day_df[["country", "state_name", "city_name"]].drop_duplicates().itertuples(index=False):
        today_city = day_df[(day_df.country == country) & (day_df.state_name == state_name) & (day_df.city_name == city_name)]
        today_urls = set(today_city.restaurant_url)

        open_mask = ((master_df.country == country) & (master_df.state_name == state_name) &
                     (master_df.city_name == city_name) & (master_df.status == "open"))
        open_urls = set(master_df.loc[open_mask, "restaurant_url"])

        for _, row in today_city[today_city.restaurant_url.isin(today_urls - open_urls)].iterrows():
            new_rows.append({
                "restaurant_url": row.restaurant_url, "country": country, "state_name": state_name, "city_name": city_name,
                "restaurant_information": row.restaurant_information, "gmaps_url": row.gmaps_url,
                "first_seen_date": TODAY, "last_confirmed_open_date": TODAY, "status": "open", "closed_date": None
            })

        master_df.loc[master_df.restaurant_url.isin(today_urls & open_urls) & open_mask, "last_confirmed_open_date"] = TODAY
        master_df.loc[master_df.restaurant_url.isin(open_urls - today_urls) & open_mask, ["status", "closed_date"]] = ["closed", TODAY]

    return pd.concat([master_df, pd.DataFrame(new_rows)], ignore_index=True) if new_rows else master_df

# %%



if __name__ == "__main__":

    restaurants_df, number_rows, previous_number_df = scrape_restaurants()
    restaurants_df.to_excel(os.path.join(Historic_DIR, f"{TODAY}_Chipotle.xlsx"), index=False)

    number_df = merge_number(previous_number_df, number_rows)
    number_df.to_excel(os.path.join(NUMBER_DIR, f"{TODAY}_Chipotle.xlsx"), index=False)

    master_files = glob.glob(os.path.join(Current_DIR, "*.xlsx"))
    master_df = pd.read_excel(max(master_files, key=os.path.getmtime)) if master_files else None
    master_df = update_open_closed_status(restaurants_df, master_df)
    master_df.to_excel(os.path.join(Current_DIR, f"{TODAY}_Chipotle_state.xlsx"), index=False)
    
    latest_file = max(glob.glob(f"{Current_DIR}/*_Chipotle.xlsx"), key=os.path.getctime)
    data = pd.read_excel(latest_file)
    data.to_excel(os.path.join(BASE_DIR, "data_restaurants.xlsx"), index=False)