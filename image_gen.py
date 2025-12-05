#!/usr/bin/env python3
"""
generate_instagram_posts.py

Full final script that:
- Reads classified JSON (category -> list of items)
- For each item:
  - If title is long, ask Gemini to shorten it to a punchy headline
  - Ask Gemini to choose the best highlight phrase from the title (option C)
  - Ask Gemini to rewrite/shorten the summary into a catchy 12-15 word sentence
  - Auto-resize title font to be as large as possible without overflowing margins
  - Embed a yellow highlight behind the chosen phrase inside the first title line
  - Place the cleaned short summary below the title, left-justified, using remaining area
  - Save images into generated_posts/<Category>/post_<n>.png

USAGE:
  - Set GEMINI_API_KEY in your environment or .env
  - Ensure pillow is installed: pip install pillow python-dotenv google-generativeai
  - Edit FONT paths if needed (see FONT_* variables)
  - Run: python generate_instagram_posts.py
"""

import os
import json
import textwrap
import re
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# --- Gemini client (Google Generative) ---
import google.generativeai as genai

load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in environment (.env)")

genai.configure(api_key=GEMINI_KEY)
MODEL = genai.GenerativeModel("gemini-2.5-flash-lite")

# ---------------------------
# CONFIG
# ---------------------------
IMG_W, IMG_H = 2000, 2500           # output image size (4:5)
MARGIN = 120
USERNAME = "dailytech_drops"             # change to your handle

# Font files (change if missing on your system)
# Prefer robust fonts (DejaVu, Inter, Montserrat, etc). If not available, script will fallback.
FONT_TITLE_PATH = "DejaVuSans-Bold.ttf"   # try DejaVu or Arial Bold
FONT_REGULAR_PATH = "DejaVuSans.ttf"      # try DejaVu or Arial

# Default font sizing (you can tweak)
TITLE_FONT_BASE = 400    # bigger base -> larger title (max starting size)
TITLE_FONT_MIN = 90
SUMMARY_FONT_SIZE = 80
USERNAME_FONT_SIZE = 46

HIGHLIGHT_COLOR = "#E7FF00"  # neon-yellow highlight
BACKGROUND = "#F3EED7"       # light beige

# Input JSON (classified output from your pipeline)
INPUT_JSON = "output/classified_educational_content.json"
OUTPUT_DIR = "generated_posts"

# Safety: max characters for Gemini calls
GEMINI_MAX_TOKENS = 256


# ---------------------------
# Utilities: Safe font loader
# ---------------------------
def load_font(path, size):
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        # fallback to default PIL font (not ideal visually)
        print(f"⚠ Warning: font '{path}' not found. Falling back to default font.")
        return ImageFont.load_default()


# ---------------------------
# Gemini helpers
# ---------------------------
def gemini_choose_highlight(title):
    """
    Use Gemini to select a short highlight phrase (1-4 words) from the title.
    Returns the phrase (string). If Gemini fails, returns the single strongest word (heuristic).
    """
    prompt = f"""From this title, choose the most important short phrase (1-4 words)
that best captures the core idea. Output ONLY the phrase, nothing else.

Title:
{title}
"""
    try:
        resp = MODEL.generate_content(prompt)
        phrase = resp.text.strip().splitlines()[0].strip()
        # sanitize phrase length
        if len(phrase.split()) > 5 or len(phrase) == 0:
            raise Exception("unexpected phrase")
        return phrase
    except Exception:
        # fallback heuristic: pick 1-2 word proper noun or first meaningful word
        tokens = re.findall(r"[A-Za-z0-9]+", title)
        if not tokens:
            return title.split()[0] if title.split() else title
        # prefer capitalized token or first token
        for t in tokens:
            if t[0].isupper():
                return t
        return tokens[0]


def gemini_shorten_summary(summary):
    """
    Use Gemini to rewrite the summary into a catchy 12-15 word sentence.
    If Gemini fails, fallback to trimming to first 15 words.
    """
    prompt = f"""Rewrite the following into a clear, factual, catchy 12–15 word summary
suitable as an Instagram caption subtitle. Keep it factual and do not add new claims.

Original:
{summary}

Output (one sentence, 12-15 words):
"""
    try:
        resp = MODEL.generate_content(prompt)
        out = resp.text.strip().replace("\n", " ").strip()
        # simple sanitize
        out = re.sub(r"\s+", " ", out)
        words = out.split()
        if len(words) < 6:
            # too short -> fallback
            raise Exception("too short")
        # cap to 15 words
        return " ".join(words[:15])
    except Exception:
        words = re.sub(r"<.*?>", "", summary).split()
        return " ".join(words[:15])


# ---------------------------
# Text/layout helpers
# ---------------------------
def wrap_text_by_width(draw, text, font, max_width):
    """
    Wrap text into lines such that each line fits within max_width using the given font.
    Returns list of lines.
    """
    words = text.split()
    if not words:
        return []
    lines = []
    cur = words[0]
    for w in words[1:]:
        test = cur + " " + w
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def fit_font_for_width(draw, text, font_path, start_size, max_width, min_size=TITLE_FONT_MIN):
    """
    Return a font object sized to fit the longest line of text within max_width.
    Decreases size in steps until it fits or reaches min_size.
    """
    size = start_size
    while size >= min_size:
        font = load_font(font_path, size)
        # test longest token (we will wrap later, but this gives a baseline)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] <= max_width:
            return font
        size -= 6
    return load_font(font_path, min_size)


# ---------------------------
# Main image generation
# ---------------------------
def create_post_image(item, index, category):
    """
    item: dict with keys: 'title', 'summary', etc.
    Saves image to generated_posts/<category>/post_<index>.png
    """
    title_original = item.get("title", "").strip() or "No Title"
    summary_raw = item.get("summary", "").strip() or ""

    # If title too long, ask Gemini to shorten (preserve meaning)
    if len(title_original) > 120:
        try:
            # request a concise 6-10 word headline
            prompt = f"""Shorten this title into a crisp 6-10 word headline.
Keep the original meaning; do not invent facts.
Title:
{title_original}

Return only the headline."""
            resp = MODEL.generate_content(prompt)
            headline = resp.text.strip().splitlines()[0].strip()
            if len(headline) < 6:
                # fallback
                headline = title_original
        except Exception:
            headline = title_original
    else:
        headline = title_original

    # Choose highlight phrase via Gemini (option C)
    highlight = gemini_choose_highlight(headline)

    # Shorten/clean summary to 12-15 words with Gemini
    short_summary = gemini_shorten_summary(summary_raw)

    # Prepare canvas
    img = Image.new("RGB", (IMG_W, IMG_H), BACKGROUND)
    draw = ImageDraw.Draw(img)

    # Fonts (we will adjust title font size dynamically)
    # Username
    font_user = load_font(FONT_REGULAR_PATH, USERNAME_FONT_SIZE)
    # summary fixed font
    font_summary = load_font(FONT_REGULAR_PATH, SUMMARY_FONT_SIZE)

    # Draw username + underline
    draw.text((MARGIN, MARGIN // 1.5), USERNAME, font=font_user, fill="black")
    line_y = MARGIN // 1.5 + draw.textbbox((0, 0), USERNAME, font=font_user)[3] + 18
    draw.line((MARGIN, line_y, IMG_W - MARGIN, line_y), fill="black", width=3)

    # Title area max width
    content_max_w = IMG_W - 2 * MARGIN

    # Fit a large title font (start from TITLE_FONT_BASE)
    font_title = fit_font_for_width(draw, headline, FONT_TITLE_PATH, TITLE_FONT_BASE, content_max_w)
    # Now wrap headline with that font
    title_lines = wrap_text_by_width(draw, headline, font_title, content_max_w)

    # If title lines are too many and appear tiny, try to increase wrapping width (less lines)
    # We'll allow up to 5 lines of title; if more, decrease font a bit to tighten width
    if len(title_lines) > 5:
        # reduce font until lines <=5 or minimal size
        size = font_title.size if hasattr(font_title, "size") else TITLE_FONT_BASE
        while len(title_lines) > 5 and size > TITLE_FONT_MIN:
            size -= 8
            font_title = load_font(FONT_TITLE_PATH, size)
            title_lines = wrap_text_by_width(draw, headline, font_title, content_max_w)

    # compute heights
    title_heights = [draw.textbbox((0, 0), line, font=font_title)[3] for line in title_lines]
    total_title_h = sum(title_heights) + (len(title_lines) - 1) * 18

    # prepare summary lines wrapped in smaller width to look neat
    summary_lines = wrap_text_by_width(draw, short_summary, font_summary, content_max_w // 1)  # full width

    summary_heights = [draw.textbbox((0, 0), line, font=font_summary)[3] for line in summary_lines]
    total_summary_h = sum(summary_heights) + (len(summary_lines) - 1) * 10

    # reserved spacing between title and summary
    gap = 60

    # total content height
    total_content_h = total_title_h + gap + total_summary_h

    # Decide top y to reduce empty space:
    # If content small, place it a bit lower so it doesn't look stuck at top.
    # We'll set top_padding so content sits around upper-third area.
    available = IMG_H - 2 * MARGIN
    if total_content_h < available * 0.6:
        top_y = int(MARGIN + (available * 0.15))  # move slightly down
    else:
        top_y = MARGIN + 40

    y = top_y

    # Draw title lines, embedding highlight when it appears on a line
    for i, line in enumerate(title_lines):
        # if highlight appears in this line, draw with highlight box
        if highlight and highlight in line:
            # draw before, highlight, after
            before, match, after = line.partition(highlight)
            # draw before
            draw.text((MARGIN, y), before, font=font_title, fill="black")
            w_before = draw.textbbox((0, 0), before, font=font_title)[2]
            # highlight box
            w_match = draw.textbbox((0, 0), match, font=font_title)[2]
            h_match = draw.textbbox((0, 0), match, font=font_title)[3]
            box_x0 = MARGIN + w_before - 8
            box_y0 = y - 6
            box_x1 = MARGIN + w_before + w_match + 8
            box_y1 = y + h_match + 6
            draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=HIGHLIGHT_COLOR)
            # draw match
            draw.text((MARGIN + w_before, y), match, font=font_title, fill="black")
            # draw after
            draw.text((MARGIN + w_before + w_match, y), after, font=font_title, fill="black")
        else:
            draw.text((MARGIN, y), line, font=font_title, fill="black")

        y += draw.textbbox((0, 0), line, font=font_title)[3] + 18

    # space between title and summary
    y += gap

    # Draw summary left-justified at remaining area
    for line in summary_lines:
        draw.text((MARGIN, y), line, font=font_summary, fill="black")
        y += draw.textbbox((0, 0), line, font=font_summary)[3] + 10

    # Small finishing: if there's still a lot of empty space below and font can be bigger, we could scale up summary slightly.
    # (Optional) Not doing aggressive changes to maintain consistent look.

    # Save path
    safe_cat = re.sub(r"[^\w\-]", "_", category) if category else "uncategorized"
    out_dir = os.path.join(OUTPUT_DIR, safe_cat)
    os.makedirs(out_dir, exist_ok=True)
    safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", title_original)[:40]
    out_path = os.path.join(out_dir, f"post_{index}_{safe_title}.png")
    img.save(out_path)
    print(f"Saved -> {out_path}")
    return out_path


# ---------------------------
# Entrypoint
# ---------------------------
def generate_all(input_json_path=INPUT_JSON):
    if not os.path.exists(input_json_path):
        raise FileNotFoundError(f"Input JSON not found: {input_json_path}")

    with open(input_json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    total = 0
    for category, items in data.items():
        print(f"Processing category: {category} ({len(items)} items)")
        for i, it in enumerate(items):
            create_post_image(it, i + 1, category)
            total += 1
    print(f"Done — {total} images generated in {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_all()
