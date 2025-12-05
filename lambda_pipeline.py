import requests
from bs4 import BeautifulSoup
import feedparser

import json
import os
from urllib.parse import urljoin
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
import boto3

# ----------------------
# CONFIGURE GEMINI API
# ----------------------
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-lite")

# Ensure directories exist (safe, does not change core logic)
os.makedirs("data", exist_ok=True)
os.makedirs("output", exist_ok=True)

# Track last uploaded S3 URI for the latest scraped file
LAST_SCRAPED_S3_URI = None
LAST_CLASSIFIED_S3_URI = None

def upload_to_s3(local_path, bucket, key=None):
    """Upload a file to S3 and return the s3:// URI. Returns None on failure."""
    try:
        s3 = boto3.client("s3")
        if key is None:
            key = os.path.basename(local_path)
        s3.upload_file(local_path, bucket, key)
        s3_uri = f"s3://{bucket}/{key}"
        print(f"✅ Uploaded to S3 → {s3_uri}")
        return s3_uri
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")
        return None

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
    scrape_date = datetime.utcnow().strftime("%Y%m%d")
    output_filename = f"data/hybrid_scraped_filtered_{scrape_date}.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)
    print(f"\n✅ DONE → Saved to {output_filename}\n")

    # If S3 bucket is configured, upload the output JSON to S3 as well
    global LAST_SCRAPED_S3_URI
    s3_bucket = os.getenv("S3_BUCKET")
    if s3_bucket:
        # use the same filename as key by default
        key = os.path.basename(output_filename)
        s3_uri = upload_to_s3(output_filename, s3_bucket, key=key)
        if s3_uri:
            LAST_SCRAPED_S3_URI = s3_uri
    
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
    with open(input_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    print(f"📦 Total items to process: {len(items)}")
    print("⚡ Processing in ONE Gemini API call...")
    result_text = generate_batch_content(items)
    output_filename = "output/educational_content.txt"
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
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    print("Classification complete! Saved to:", output_json_path)

    # upload classified JSON to S3 if configured
    global LAST_CLASSIFIED_S3_URI
    s3_bucket = os.getenv("S3_BUCKET")
    if s3_bucket:
        key = os.path.basename(output_json_path)
        s3_uri = upload_to_s3(output_json_path, s3_bucket, key=key)
        if s3_uri:
            LAST_CLASSIFIED_S3_URI = s3_uri
    return output_json_path

# ------------------------------------------------------
# AWS Lambda handler wrapper
# Supported event values:
# {"action":"scrape"|"process"|"classify"|"all", "extra_sites": [...], "input_path": "...", "output_path": "..."}
# ------------------------------------------------------
def lambda_handler(event, context):
    # default action: run all (scrape -> process -> classify)
    action = None
    if isinstance(event, dict):
        action = event.get("action")
    if not action:
        action = "all"

    result = {"action": action}
    try:
        if action == "scrape":
            extra = event.get("extra_sites") if isinstance(event, dict) else None
            scraped = run_scraper(extra_sites=extra)
            # include S3 URI if upload occurred
            if LAST_SCRAPED_S3_URI:
                result["scraped_s3_uri"] = LAST_SCRAPED_S3_URI
            result["scraped_path"] = scraped
            result["status"] = "scrape_completed"

        elif action == "process":
            input_path = event.get("input_path") if isinstance(event, dict) else None
            if not input_path:
                return {"error": "input_path required for process action"}
            proc_out = run_processing(input_path)
            result["processed_path"] = proc_out
            result["status"] = "process_completed"

        elif action == "classify":
            input_path = event.get("input_path") if isinstance(event, dict) else None
            output_path = event.get("output_path") if isinstance(event, dict) else None
            if not input_path or not output_path:
                return {"error": "input_path and output_path required for classify action"}
            cls_out = run_classification(input_path, output_path)
            result["classified_path"] = cls_out
            result["status"] = "classify_completed"

        elif action == "all":
            extra = event.get("extra_sites") if isinstance(event, dict) else None
            scraped = run_scraper(extra_sites=extra)
            if LAST_SCRAPED_S3_URI:
                result["scraped_s3_uri"] = LAST_SCRAPED_S3_URI
            proc = run_processing(scraped)
            classified = run_classification(scraped, f"output/classified_educational_content.json", text_key="summary")
            if LAST_CLASSIFIED_S3_URI:
                result["classified_s3_uri"] = LAST_CLASSIFIED_S3_URI
            result.update({"scraped_path": scraped, "processed_path": proc, "classified_path": classified})
            result["status"] = "all_completed"

        else:
            result["status"] = "unknown_action"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


if __name__ == "__main__":
    # Keep original local behavior: run all steps in sequence
    scraped_json = run_scraper()
    run_processing(scraped_json)
    classify_output = run_classification(scraped_json, f"output/classified_educational_content.json", text_key="summary")
    print("All steps complete. Final classified output:", classify_output)
