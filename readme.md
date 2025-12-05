# Tech Trend Auto Publisher

This project is an automated pipeline for scraping, processing, and classifying technology news, with a FastAPI backend and a simple HTML/JS frontend. It is designed for easy deployment (including AWS Lambda) and provides both API and web-based access to the processed content.

## Features
- **Scrape**: Collects tech news from default and optional extra RSS/news sources.
- **Process**: Cleans and processes scraped data (default: `data/rss_data.json`).
- **Classify**: Classifies processed data and writes results to `output/educational_content.txt`.
- **API**: FastAPI backend with endpoints for scraping, processing, classifying, viewing, and downloading results.
- **Frontend**: Simple HTML/JS frontend to trigger pipeline steps and view/download results.
- **AWS Lambda Ready**: Code is structured for Lambda deployment (ZIP or container image).

## Project Structure
```
├── main_pipeline.py         # Core scraping, processing, classification logic
├── fastapi_app.py           # FastAPI backend
├── requirements.txt         # Python dependencies
├── index.html               # Frontend (HTML/JS/CSS)
├── data/
│   └── rss_data.json        # Default input for processing
├── output/
│   └── educational_content.txt # Output file for classified content
```

## Usage

### 1. Backend (FastAPI)
```bash
pip install -r requirements.txt
uvicorn fastapi_app:app
```

### 2. Frontend
Open `index.html` in your browser. Use the forms to trigger scraping, processing, and classification. View or download the output file directly from the page.

### 3. Lambda Deployment
- Use `lambda_pipeline.py` for AWS Lambda (ZIP or container image).
- See Dockerfile for container deployment.

## API Endpoints
- `POST /scrape` — Scrape news (optionally pass extra sites)
- `POST /process` — Process data (uses default input file)
- `POST /classify` — Classify data (uses default input/output files)
- `GET /view_output` — View output file content as JSON
- `GET /download_output` — Download output file

## Customization
- To add more sources, edit the scraping logic or pass extra sites via the frontend.
- To change input/output files, modify the backend code or folder structure as needed.

## License
MIT
