from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Tuple
import re

app = FastAPI(title="Student Academic Profile API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


students: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

VALID_STATUSES = {"completed", "in-progress", "attempted"}


class HistoryPayload(BaseModel):
    history: List[Dict[str, Any]]


class PlanPayload(BaseModel):
    planned_courses: List[Dict[str, Any]]


def clean_text(value: Any) -> str:
    return " ".join(str(value).replace("\xa0", " ").split())


def normalize_header(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("·", " ").replace("_", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9 ]+", "", value).strip()


def to_int_credits(value: Any) -> int:
    text = clean_text(value)
    match = re.search(r"\d+", text)
    if not match:
        return 0
    return int(match.group(0))


def extract_course_code(course_cell_text: str) -> str:
   

    text = clean_text(course_cell_text)
    match = re.search(r"\b[A-Za-z]{2,10}[-\s]?\d{3,5}[A-Za-z]?\b", text)
    if match:
        code = match.group(0).upper().replace(" ", "-")
        return code
    return text


def grade_score(grade: Any) -> Tuple[int, float]:

    text = clean_text(grade).upper()
    if not text:
        return (0, 0.0)

    num = re.search(r"\d+(?:\.\d+)?", text)
    if num:
        return (3, float(num.group(0)))

    letter_values = {
        "A+": 12, "A": 11, "A-": 10,
        "B+": 9, "B": 8, "B-": 7,
        "C+": 6, "C": 5, "C-": 4,
        "D+": 3, "D": 2, "D-": 1,
        "F": 0,
    }
    if text in letter_values:
        return (2, float(letter_values[text]))

    if text in {"P", "PASS", "PASSED", "CR", "CREDIT"}:
        return (1, 1.0)

    return (0, 0.0)


def find_column_indexes(headers: List[str]) -> Dict[str, int]:
    normalized = [normalize_header(h) for h in headers]
    indexes: Dict[str, int] = {}

    for i, header in enumerate(normalized):
        if "status" in header and "status" not in indexes:
            indexes["status"] = i
        elif "course" in header and "course" not in indexes:
            indexes["course"] = i
        elif "grade" in header and "grade" not in indexes:
            indexes["grade"] = i
        elif "term" in header and "term" not in indexes:
            indexes["term"] = i
        elif "credit" in header and "credits" not in indexes:
            indexes["credits"] = i

    required = {"status", "course", "grade", "term", "credits"}
    if not required.issubset(indexes):
        return {}
    return indexes


def parse_transcript_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    deduped: Dict[Tuple[str, str], Tuple[Tuple[int, float], int, Dict[str, Any]]] = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_indexes: Dict[str, int] = {}
        data_start_index = 0

        # Find the header row in this table, not necessarily the first row
        for row_index, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            headers = [cell.get_text(" ") for cell in cells]
            possible = find_column_indexes(headers)
            if possible:
                header_indexes = possible
                data_start_index = row_index + 1
                break

        if not header_indexes:
            continue

        max_col = max(header_indexes.values())

        for row in rows[data_start_index:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max_col:
                continue

            status = clean_text(cells[header_indexes["status"]].get_text(" "))
            course_text = clean_text(cells[header_indexes["course"]].get_text(" "))
            grade = clean_text(cells[header_indexes["grade"]].get_text(" "))
            term = clean_text(cells[header_indexes["term"]].get_text(" "))
            credits = to_int_credits(cells[header_indexes["credits"]].get_text(" "))

            if not status or normalize_header(status) not in VALID_STATUSES:
                continue
            if not term:
                continue
            if not course_text:
                continue

            course_code = extract_course_code(course_text)
            record = {
                "course_code": course_code,
                "term": term,
                "credits_earned": credits,
                "status": status,
            }

            key = (course_code, term)
            score = grade_score(grade)
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = (score, credits, record)
            else:
                old_score, old_credits, _ = existing
                if score > old_score or (score == old_score and credits > old_credits):
                    deduped[key] = (score, credits, record)

    #Stable deterministic order makes testing easier
    records = [item[2] for item in deduped.values()]
    records.sort(key=lambda r: (str(r["term"]), str(r["course_code"])))
    return records


def require_student(student_id: str) -> Dict[str, List[Dict[str, Any]]]:
    if student_id not in students:
        raise HTTPException(status_code=404, detail="Student not found")
    return students[student_id]


@app.get("/")
def root():
    return {"status": "ok", "message": "Student Academic Profile API is running"}


@app.post("/api/v1/students/{student_id}/history/import", status_code=201)
async def import_history(student_id: str, file: UploadFile = File(...)):
    content = await file.read()
    html = content.decode("utf-8", errors="ignore")
    history = parse_transcript_html(html)

    students[student_id] = {
        "history": history,
        "plan": students.get(student_id, {}).get("plan", []),
    }
    return {"status": "success", "past_courses_imported": len(history)}


@app.put("/api/v1/students/{student_id}/history")
def update_history(student_id: str, payload: HistoryPayload):
    student = require_student(student_id)
    student["history"] = payload.history
    return {"status": "success", "message": "Academic history updated successfully"}


@app.delete("/api/v1/students/{student_id}/history")
def delete_history(student_id: str):
    student = require_student(student_id)
    student["history"] = []
    return {"status": "success", "message": "Academic history cleared successfully"}


@app.post("/api/v1/students/{student_id}/plan")
def create_plan(student_id: str, payload: PlanPayload):
    student = require_student(student_id)
    student["plan"] = payload.planned_courses
    return {"status": "success", "planned_courses_saved": len(payload.planned_courses)}


@app.put("/api/v1/students/{student_id}/plan")
def update_plan(student_id: str, payload: PlanPayload):
    student = require_student(student_id)
    student["plan"] = payload.planned_courses
    return {"status": "success", "planned_courses_saved": len(payload.planned_courses)}


@app.delete("/api/v1/students/{student_id}/plan")
def delete_plan(student_id: str):
    student = require_student(student_id)
    student["plan"] = []
    return {"status": "success", "message": "Plan cleared successfully"}


@app.get("/api/v1/students/{student_id}/profile")
def get_profile(student_id: str):
    student = require_student(student_id)
    # Return exactly these three top-level keys.
    return {
        "student_id": student_id,
        "history": student["history"],
        "plan": student["plan"],
    }
