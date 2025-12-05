from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
from main_pipeline import run_scraper, run_processing, run_classification
from image_gen import create_post_image
from instagram_utils import post_image_to_instagram

app = FastAPI()

# Mount the generated_posts directory to serve images
os.makedirs("generated_posts", exist_ok=True)
app.mount("/generated_posts", StaticFiles(directory="generated_posts"), name="generated_posts")

# Allow all origins for development; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    extra_sites: Optional[List[str]] = None

class ProcessRequest(BaseModel):
    pass

class ClassifyRequest(BaseModel):
    text_key: Optional[str] = "summary"

class GenerateImagesRequest(BaseModel):
    items: List[Dict[str, Any]]
    category: str = "General"

class InstagramPostRequest(BaseModel):
    items: List[Dict[str, Any]] # Should contain 'image_url' and 'summary'/'title'
    access_token: str
    instagram_account_id: Optional[str] = None

class RunAllRequest(BaseModel):
    extra_sites: Optional[List[str]] = None
    text_key: Optional[str] = "summary"

@app.post("/scrape")
def scrape(req: ScrapeRequest):
    scraped_path = run_scraper(extra_sites=req.extra_sites)
    return {"scraped_path": scraped_path}

@app.post("/process")
def process(_: ProcessRequest):
    input_path = os.path.join("data", "hybrid_scraped_data.json")
    if not os.path.exists(input_path):
        return {"error": f"Input file not found: {input_path}. Please run the scraper first."}
    try:
        processed_path = run_processing(input_path)
        return {"processed_path": processed_path}
    except Exception as e:
        return {"error": str(e)}

@app.post("/classify")
def classify(req: ClassifyRequest):
    input_path = os.path.join("data", "hybrid_scraped_data.json")
    output_path = os.path.join("output", "educational_content.txt")
    if not os.path.exists(input_path):
        return {"error": f"Input file not found: {input_path}. Please run the scraper and processing steps first."}
    try:
        classified_path = run_classification(input_path, output_path, text_key=req.text_key)
        return {"classified_path": classified_path}
    except Exception as e:
        return {"error": str(e)}

@app.post("/generate_images")
def generate_images(req: GenerateImagesRequest):
    """
    Generate images for the provided list of items.
    Returns a list of items with an added 'image_url' field.
    """
    results = []
    base_url = "http://localhost:8000" # Change this if running on a different host/port or behind ngrok
    
    for i, item in enumerate(req.items):
        try:
            # Generate image
            image_path = create_post_image(item, i + 1, req.category)
            
            # Convert local path to URL
            # image_path is like "generated_posts\Category\post_1_Title.png"
            # We need to make it relative to the mount point
            rel_path = os.path.relpath(image_path, start=os.getcwd())
            # Ensure forward slashes for URL
            rel_path = rel_path.replace("\\", "/")
            
            image_url = f"{base_url}/{rel_path}"
            
            item_with_image = item.copy()
            item_with_image["image_url"] = image_url
            item_with_image["local_path"] = image_path
            results.append(item_with_image)
        except Exception as e:
            print(f"Error generating image for item {i}: {e}")
            item_with_error = item.copy()
            item_with_error["error"] = str(e)
            results.append(item_with_error)
            
    return {"results": results}

@app.post("/post_to_instagram")
def post_to_instagram_endpoint(req: InstagramPostRequest):
    """
    Post the provided items to Instagram.
    Items must have 'image_url'.
    """
    results = []
    for item in req.items:
        if "image_url" not in item:
            results.append({"status": "failed", "error": "No image_url provided", "item": item})
            continue
            
        try:
            caption = f"{item.get('title', 'New Post')}\n\n{item.get('summary', '')}\n\n#tech #news #update"
            media_id = post_image_to_instagram(
                req.access_token, 
                item["image_url"], 
                caption, 
                req.instagram_account_id
            )
            results.append({"status": "success", "media_id": media_id, "item_title": item.get("title")})
        except Exception as e:
            results.append({"status": "failed", "error": str(e), "item_title": item.get("title")})
            
    return {"results": results}

@app.get("/view_output")
def view_output():
    output_path = os.path.join("output", "educational_content.txt")
    if not os.path.exists(output_path):
        return {"error": "Output file not found."}
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content}

@app.get("/download_output")
def download_output():
    output_path = os.path.join("output", "educational_content.txt")
    if not os.path.exists(output_path):
        return {"error": "Output file not found."}
    return FileResponse(output_path, media_type="text/plain", filename="educational_content.txt")

@app.post("/run_all")
def run_all(req: RunAllRequest):
    """
    Run all processes at once: scrape -> process -> classify
    Returns the results of each step along with any errors encountered.
    """
    results = {
        "scrape": {"status": "pending", "data": None, "error": None},
        "process": {"status": "pending", "data": None, "error": None},
        "classify": {"status": "pending", "data": None, "error": None}
    }
    
    # Step 1: Scrape
    try:
        scraped_path = run_scraper(extra_sites=req.extra_sites)
        results["scrape"]["status"] = "success"
        results["scrape"]["data"] = {"scraped_path": scraped_path}
    except Exception as e:
        results["scrape"]["status"] = "failed"
        results["scrape"]["error"] = str(e)
        return {"status": "failed", "message": "Scraping failed", "results": results}
    
    # Step 2: Process
    try:
        input_path = os.path.join("data", "hybrid_scraped_data.json")
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        processed_path = run_processing(input_path)
        results["process"]["status"] = "success"
        results["process"]["data"] = {"processed_path": processed_path}
    except Exception as e:
        results["process"]["status"] = "failed"
        results["process"]["error"] = str(e)
        return {"status": "failed", "message": "Processing failed", "results": results}
    
    # Step 3: Classify
    try:
        input_path = os.path.join("data", "hybrid_scraped_data.json")
        output_path = os.path.join("output", "educational_content.txt")
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        classified_path = run_classification(input_path, output_path, text_key=req.text_key)
        results["classify"]["status"] = "success"
        results["classify"]["data"] = {"classified_path": classified_path}
    except Exception as e:
        results["classify"]["status"] = "failed"
        results["classify"]["error"] = str(e)
        return {"status": "failed", "message": "Classification failed", "results": results}
    
    # All steps completed successfully
    return {
        "status": "success",
        "message": "All processes completed successfully",
        "results": results
    }

@app.get("/")
def root():
    return {"message": "Webscrapeer FastAPI backend is running."}
