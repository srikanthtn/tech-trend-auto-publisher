from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from main_pipeline import run_scraper, run_processing, run_classification


app = FastAPI()

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


# Remove input_path from requests; use default paths
class ProcessRequest(BaseModel):
    pass

class ClassifyRequest(BaseModel):
    text_key: Optional[str] = "summary"

@app.post("/scrape")
def scrape(req: ScrapeRequest):
    scraped_path = run_scraper(extra_sites=req.extra_sites)
    return {"scraped_path": scraped_path}


# Use default input file for processing
@app.post("/process")
def process(_: ProcessRequest):
    input_path = os.path.join("data", "rss_data.json")
    processed_path = run_processing(input_path)
    return {"processed_path": processed_path}


# Use default input/output files for classification
@app.post("/classify")
def classify(req: ClassifyRequest):
    input_path = os.path.join("data", "hybrid_scraped_data.json")
    output_path = os.path.join("output", "educational_content.txt")
    classified_path = run_classification(input_path, output_path, text_key=req.text_key)
    return {"classified_path": classified_path}

# Endpoint to view output file as JSON
@app.get("/view_output")
def view_output():
    output_path = os.path.join("output", "educational_content.txt")
    if not os.path.exists(output_path):
        return {"error": "Output file not found."}
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content}

# Endpoint to download output file
from fastapi.responses import FileResponse

@app.get("/download_output")
def download_output():
    output_path = os.path.join("output", "educational_content.txt")
    if not os.path.exists(output_path):
        return {"error": "Output file not found."}
    return FileResponse(output_path, media_type="text/plain", filename="educational_content.txt")

@app.get("/")
def root():
    return {"message": "Webscrapeer FastAPI backend is running."}
