import requests
from bs4 import BeautifulSoup
import json
import os
import feedparser
from urllib.parse import urljoin
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai

# ----------------------
# CONFIGURE GEMINI API
# ----------------------
load_dotenv() 
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-lite")

# ------------------------------------------------------
# Predefined Official Tech Websites
# ------------------------------------------------------
OFFICIAL_TECH_SITES = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com",
    "https://www.wired.com",
    "https://www.technologyreview.com",
    "https://blog.google"
]

# ------------------------------------------------------
# Allowed published date: TODAY & YESTERDAY
# ------------------------------------------------------
TODAY = datetime.utcnow().date()
YESTERDAY = TODAY - timedelta(days=1)

def is_allowed_date(pub_date_str):
    try:
        pub_dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00")).date()
    except:
        try:
            pub_dt = datetime.strptime(pub_date_str[:16], "%a, %d %b %Y").date()
        except:
            return False
    return pub_dt in (TODAY, YESTERDAY)

# ------------------------------------------------------
# Utility: Check if a URL is a valid RSS feed
# ------------------------------------------------------
def is_rss_feed(url):
    try:
        parsed = feedparser.parse(url)
        return len(parsed.entries) > 0
    except:
        return False

# ------------------------------------------------------
# Extract RSS feed data (Filtered for today/yesterday)
# ------------------------------------------------------
def scrape_rss(url):
    print(f"🔍 Using RSS feed: {url}")
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries:
        published = entry.get("published", "") or entry.get("updated", "")
        if published == "" or not is_allowed_date(published):
            continue
        items.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", ""),
            "published": published
        })
    return items

# ------------------------------------------------------
# Extract article links from HTML main page
# ------------------------------------------------------
def extract_article_links(main_url):
    print(f"🔍 Scraping main page for articles: {main_url}")
    try:
        response = requests.get(main_url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
    except:
        print("❌ Failed to load main page.")
        return []
    article_links = set()
    patterns = ["article", "post", "blog", "news"]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(p in href.lower() for p in patterns):
            full_url = urljoin(main_url, href)
            article_links.add(full_url)
    return list(article_links)

# ------------------------------------------------------
# Scrape an HTML article (with date filtering)
# ------------------------------------------------------
def scrape_article(url):
    print(f"📝 Scraping article: {url}")
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find("h1")
        title_text = title.get_text(strip=True) if title else "No Title"
        date = soup.find("time")
        pub_date = date.get("datetime") if date else "Unknown"
        if pub_date == "Unknown" or not is_allowed_date(pub_date):
            return None
        paragraphs = soup.find_all("p")
        content = "\n".join(p.get_text(strip=True) for p in paragraphs)
        return {
            "title": title_text,
            "link": url,
            "summary": content[:300] + "...",
            "published": pub_date
        }
    except:
        return None

# ------------------------------------------------------
# Hybrid scraper (RSS → HTML fallback)
# ------------------------------------------------------
def hybrid_scrape(url):
    print(f"\n🚀 Scraping website: {url}")
    common_rss = [
        url,
        url.rstrip("/") + "/feed",
        url.rstrip("/") + "/rss",
        url.rstrip("/") + "/rss.xml",
        url.rstrip("/") + "/feed.xml"
    ]
    # Try RSS first
    for rss_url in common_rss:
        if is_rss_feed(rss_url):
            return scrape_rss(rss_url)
    # Fallback → HTML scraping
    print("⚠️ No RSS found → Switching to HTML scraping")
    article_links = extract_article_links(url)
    results = []
    for link in article_links:
        data = scrape_article(link)
        if data:
            results.append(data)
    return results

# ------------------------------------------------------
# SCRAPE ALL SITES (main step 1)
# ------------------------------------------------------
def run_scraper(extra_sites=None):
    print("\n📌 Hybrid Scraper Started (Today + Yesterday Filter)\n")
    if extra_sites is None:
        extra_sites = []
    all_sites = OFFICIAL_TECH_SITES + extra_sites
    final_output = []
    for site in all_sites:
        try:
            site_data = hybrid_scrape(site)
            final_output.extend(site_data)
        except Exception as e:
            print(f"❌ Error scraping {site}: {e}")
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    output_filename = os.path.join(data_dir, "hybrid_scraped_data.json")
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)
    print(f"\n✅ DONE → Saved to {output_filename}\n")
    return output_filename

# ------------------------------------------------------
# PROCESS DATA WITH GEMINI (main step 2)
# ------------------------------------------------------
def generate_batch_content(items):
    combined = ""
    for i, item in enumerate(items):
        combined += f"""
ITEM {i+1}
TITLE: {item['title']}
CONTENT: {item['summary']}
PUBLISHED: {item.get('published', 'Unknown')}
"""
    prompt = f"""
You are an expert educator.

Your task:
- Read ALL items below.
- For EACH item, generate:
  ✓ Title (clean and simple)
  ✓ Explanation of 25-50 words
  ✓ Published Time (as provided)
- Use simple student-friendly words.
- Only factual info (no fake or assumed details).
- Keep explanations clear, meaningful, and educational.

STRICT OUTPUT FORMAT:
---
ITEM 1
Title: <title>
Published: <published time>
Explanation: <25-50 word explanation>

ITEM 2
Title: <title>
Published: <published time>
Explanation: <25-50 word explanation>

---

Now process these items:


{combined}
"""
    response = model.generate_content(prompt)
    return response.text

def run_processing(input_json_path):
    if not os.path.exists(input_json_path):
        raise FileNotFoundError(f"Input file not found: data/hybrid_scraped_data.json. Please run the scraper first.")
    with open(input_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    print(f"📦 Total items to process: {len(items)}")
    print("⚡ Processing in ONE Gemini API call...")
    result_text = generate_batch_content(items)
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_filename = os.path.join(output_dir, "educational_content.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(result_text)
    print(f"✅ Saved → {output_filename}")
    print("🎉 API usage minimized (only 1 call made!)")
    return output_filename

# ------------------------------------------------------
# SEPARATE/CLASSIFY CONTENT (main step 3)
# ------------------------------------------------------
CATEGORY_KEYWORDS = {
    "Learning & Skills": [
        "ai", "coding", "programming", "notes", "exam", "study",
        "machine learning", "python", "deep learning", "skill"
    ],
    "Career & Productivity": [
        "career", "job", "productivity", "resume", "interview",
        "time management", "work", "focus"
    ],
    "Motivation & Mindset": [
        "motivation", "mindset", "inspiration", "discipline",
        "success", "confidence", "habit"
    ],
    "Tools & Resources": [
        "tools", "apps", "websites", "resources", "ai tools",
        "extensions", "software"
    ],
}

def classify_content(text):
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category
    return "Other"

def run_classification(input_json_path, output_json_path, text_key="summary"):
    if not os.path.exists(input_json_path):
        raise FileNotFoundError(f"Input file not found: {input_json_path}. Please run the scraper and processing steps first.")
    with open(input_json_path, "r", encoding="utf-8") as f:
        content_list = json.load(f)
    result = {
        "Learning & Skills": [],
        "Career & Productivity": [],
        "Motivation & Mindset": [],
        "Tools & Resources": [],
        "Other": []
    }
    for item in content_list:
        if isinstance(item, dict):
            text = item.get(text_key, "")
        else:
            text = str(item)
        category = classify_content(text)
        result[category].append(item)
    output_dir = os.path.dirname(output_json_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    print("Classification complete! Saved to:", output_json_path)
    return output_json_path

# ------------------------------------------------------
# MAIN PIPELINE RUNNER
# ------------------------------------------------------
if __name__ == "__main__":
    # Step 1: Scrape
    scraped_json = run_scraper()
    # Step 2: Process (always use 'data/hybrid_scraped_data.json')
    processed_txt = run_processing("data/hybrid_scraped_data.json")
    # Step 3: Classify (always use 'data/hybrid_scraped_data.json')
    classify_output = run_classification("data/hybrid_scraped_data.json", "output/classified_educational_content.json", text_key="summary")
    print("All steps complete. Final classified output:", classify_output)
