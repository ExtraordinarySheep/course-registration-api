from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from typing import Dict, Any

app = FastAPI(title="Course Catalog API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage. Render keeps this while the service process is running.
catalog: Dict[str, Dict[str, Any]] = {}


def normalize_course_code(code: str) -> str:
    """Make COSC 3506, COSC3506, and COSC%203506 match the same key."""
    return "".join(str(code).strip().upper().split())


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def parse_catalog_html(html: str) -> Dict[str, Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("No table found in uploaded HTML file.")

    rows = table.find_all("tr")
    if len(rows) < 2:
        raise ValueError("Course table does not contain data rows.")

    parsed: Dict[str, Dict[str, Any]] = {}

    # Skip header row. Read cells by position so the parser works for hidden catalogs too.
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        course_code = clean_text(cells[0].get_text(" "))
        title = clean_text(cells[1].get_text(" "))
        credits_text = clean_text(cells[2].get_text(" "))
        prerequisites = clean_text(cells[3].get_text(" "))
        cross_listed = clean_text(cells[4].get_text(" "))

        if not course_code:
            continue

        try:
            credits = int(credits_text)
        except ValueError:
            try:
                credits = float(credits_text)
            except ValueError:
                credits = credits_text

        course = {
            "course_code": course_code,
            "title": title,
            "credits": credits,
            "prerequisites": prerequisites,
            "cross_listed": cross_listed,
        }
        parsed[normalize_course_code(course_code)] = course

    if not parsed:
        raise ValueError("No valid courses found in the uploaded HTML file.")
    return parsed


@app.get("/")
def root():
    return {"status": "ok", "message": "Course Catalog API is running"}


@app.post("/api/v1/admin/catalog/import")
async def import_catalog(file: UploadFile = File(...)):
    try:
        content = await file.read()
        html = content.decode("utf-8", errors="ignore")
        parsed = parse_catalog_html(html)
        catalog.clear()
        catalog.update(parsed)
        return {"status": "success", "imported": len(parsed)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/v1/catalog/courses/{course_code}")
def get_course(course_code: str):
    key = normalize_course_code(course_code)
    course = catalog.get(key)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    # Return exactly the five required keys.
    return {
        "course_code": course["course_code"],
        "title": course["title"],
        "credits": course["credits"],
        "prerequisites": course["prerequisites"],
        "cross_listed": course["cross_listed"],
    }
