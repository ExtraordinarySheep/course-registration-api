# Course Catalog API

FastAPI project for Phase 1: Environment Setup & Catalog Ingestion.

## Install

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
pip install -r requirements.txt
```

## Run locally

```bash
uvicorn main:app --reload
```

## Test locally

Import the HTML catalog:

```bash
curl -X POST -F "file=@sample_catalog.html;type=text/html" http://localhost:8000/api/v1/admin/catalog/import
```

Get a course without a space:

```bash
curl http://localhost:8000/api/v1/catalog/courses/COSC3506
```

Get a course with encoded space:

```bash
curl http://localhost:8000/api/v1/catalog/courses/COSC%203506
```

Expected JSON keys:

```json
{
  "course_code": "COSC 3506",
  "title": "Software Systems Development",
  "credits": 3,
  "prerequisites": "COSC 2007",
  "cross_listed": "ITEC 3506"
}
```

## Render deployment

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

After deployment, replace the placeholder in `api_url.txt` with your Render base URL only, for example:

```text
https://sylviayi.onrender.com
```

Do not include a trailing slash or endpoint path.
