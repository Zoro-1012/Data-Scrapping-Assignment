import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

BASE_URL = "https://www.ambitionbox.com/list-of-companies?page={}"

KNOWN_INDUSTRIES = [
    "IT Services & Consulting", "Financial Services", "Internet",
    "Education & Training", "BPO", "Retail", "Healthcare",
    "Manufacturing", "Automobile", "Telecom", "Media",
    "Insurance", "Real Estate", "FMCG", "Logistics",
    "Engineering & Construction", "Analytics & KPO", "Banking",
    "Pharma", "Energy", "Government", "NGO"
]


# ---------- STAGE 1 : LISTING PAGE SCRAPER ----------

def scrape_listing_page(page_number):

    url = BASE_URL.format(page_number)
    print(f"\nFetching page {page_number}: {url}")

    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.text, "html.parser")

    cards = soup.find_all("div", class_="companyCardWrapper")
    print(f"Found {len(cards)} companies on page {page_number}")

    companies = []
    for card in cards:
        name = card.find("meta", itemprop="name")
        profile_url = card.find("meta", itemprop="url")
        if name and profile_url:
            companies.append({
                "name": name["content"],
                "profile_url": profile_url["content"]
            })

    return companies


# ---------- STAGE 2 : COMPANY PROFILE SCRAPER ----------

def scrape_company_profile(url):

    print(f"Scraping: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # ---------- Overall Rating ----------
        rating = "N/A"
        rating_tag = soup.find("span", class_="text-primary-text")
        if rating_tag:
            rating = rating_tag.get_text(strip=True)

        # ---------- Review Count ----------
        review_count = "N/A"
        review_link = soup.find("a", href=lambda x: x and "/reviews/" in x)
        if review_link:
            count_div = review_link.find("div", class_="text-primary-text")
            if count_div:
                review_count = count_div.get_text(strip=True)

        # ---------- Description ----------
        description = "N/A"
        for i, line in enumerate(lines):
            if "Company Summary" in line and i + 1 < len(lines):
                description = lines[i + 1]
                break

        # ---------- Industry ----------
        industries = []
        for line in lines:
            if line in KNOWN_INDUSTRIES:
                industries.append(line)
        industry = ", ".join(dict.fromkeys(industries)) if industries else "N/A"

        if industry == "N/A":
            inter = soup.find("span", class_="companyCardWrapper__interLinking")
            if inter:
                text_parts = inter.get_text(strip=True).split("|")
                if text_parts:
                    industry = text_parts[0].strip()

        # ---------- Key Ratings ----------
        key_rating_labels = ["Salary", "Job security", "Work-life balance", "Company culture"]
        key_ratings = {label: "N/A" for label in key_rating_labels}

        for i, line in enumerate(lines):
            if line in key_rating_labels and i > 0:
                prev = lines[i - 1]
                try:
                    float(prev)
                    key_ratings[line] = prev
                except ValueError:
                    pass

        return {
            "name": "N/A",
            "profile_url": url,
            "rating": rating,
            "review_count": review_count,
            "industry": industry,
            "description": description,
            "salary_rating": key_ratings["Salary"],
            "job_security_rating": key_ratings["Job security"],
            "work_life_balance_rating": key_ratings["Work-life balance"],
            "company_culture_rating": key_ratings["Company culture"],
        }

    except Exception as e:
        print(f"  ERROR scraping {url}: {e}")
        return None


# ---------- SCRAPE ALL LISTING PAGES ----------

all_companies = []

for page in range(1, 6):
    companies = scrape_listing_page(page)
    all_companies.extend(companies)
    time.sleep(2)

all_companies = all_companies[:50]
print(f"\nTotal companies to scrape: {len(all_companies)}")


# ---------- SCRAPE ALL PROFILE PAGES ----------

all_data = []

for i, company in enumerate(all_companies):
    print(f"\n[{i+1}/50]", end=" ")
    profile = scrape_company_profile(company["profile_url"])

    if profile:
        profile["name"] = company["name"]
        all_data.append(profile)

    time.sleep(2)


# ---------- SAVE CORE CSV (ASSIGNMENT REQUIREMENT) ----------

df = pd.DataFrame(all_data)

df = df[[
    "name", "profile_url", "rating", "review_count",
    "industry", "description",
    "salary_rating", "job_security_rating",
    "work_life_balance_rating", "company_culture_rating"
]]

df.to_csv("companies.csv", index=False)
print(f"\n✅ Done! Saved {len(df)} companies to companies.csv")


# ============================================================
# BONUS SECTION — EXTRA ANALYSIS (BEYOND ASSIGNMENT REQUIREMENTS)
# These columns and insights were added to demonstrate
# data enrichment on top of raw scraping.
# ============================================================

print("\n⭐ Running bonus analysis...")

# Convert rating column to numeric for calculations
df["rating_numeric"] = pd.to_numeric(df["rating"], errors="coerce")


# --- BONUS 1: Performance label based on overall rating ---

def label_performance(rating):
    if pd.isna(rating):
        return "N/A"
    elif rating >= 4.0:
        return "Excellent"
    elif rating >= 3.5:
        return "Good"
    elif rating >= 3.0:
        return "Average"
    else:
        return "Below Average"

df["performance"] = df["rating_numeric"].apply(label_performance)


# --- BONUS 2: Best and worst rated category per company ---

def best_and_worst(row):
    scores = {
        "Salary":            row["salary_rating"],
        "Job Security":      row["job_security_rating"],
        "Work-Life Balance": row["work_life_balance_rating"],
        "Company Culture":   row["company_culture_rating"],
    }
    # Only consider rows that have actual numeric values
    numeric = {k: float(v) for k, v in scores.items() if v != "N/A"}
    if not numeric:
        return "N/A", "N/A"
    return max(numeric, key=numeric.get), min(numeric, key=numeric.get)

df["best_rated_for"], df["worst_rated_for"] = zip(*df.apply(best_and_worst, axis=1))


# --- BONUS 3: Convert review counts to real integers ---
# e.g. "1.1L" -> 110000, "73.5k" -> 73500

def parse_review_count(value):
    if value == "N/A":
        return None
    value = value.strip().replace(",", "")
    try:
        if "L" in value:
            return int(float(value.replace("L", "")) * 100000)
        elif "k" in value:
            return int(float(value.replace("k", "")) * 1000)
        else:
            return int(value)
    except:
        return None

df["review_count_numeric"] = df["review_count"].apply(parse_review_count)


# --- Save enriched CSV with bonus columns ---

bonus_df = df[[
    "name", "profile_url", "rating", "review_count", "review_count_numeric",
    "industry", "description",
    "salary_rating", "job_security_rating",
    "work_life_balance_rating", "company_culture_rating",
    "performance", "best_rated_for", "worst_rated_for"
]]

bonus_df.to_csv("companies_enriched.csv", index=False)
print("⭐ Bonus analysis saved to companies_enriched.csv")


# --- Print a quick summary ---
print("\n--- Quick Insights from Bonus Analysis ---")
print(f"Top rated company:    {df.loc[df['rating_numeric'].idxmax(), 'name']} "
      f"({df['rating_numeric'].max()})")
print(f"Lowest rated company: {df.loc[df['rating_numeric'].idxmin(), 'name']} "
      f"({df['rating_numeric'].min()})")
print(f"\nPerformance breakdown:")
print(df["performance"].value_counts().to_string())