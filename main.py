from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Course Registration API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

catalog: dict[str, dict[str, Any]] = {}
students: dict[str, dict[str, list[dict[str, Any]]]] = {}

VALID_STATUSES = {"completed", "in-progress", "attempted"}
GRADUATION_TARGET = 120


class HistoryPayload(BaseModel):
    history: list[dict[str, Any]]


class PlanPayload(BaseModel):
    planned_courses: list[dict[str, Any]]


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def normalize_header(value: str) -> str:
    text = clean_text(value).lower()
    text = text.replace("·", " ").replace("_", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9 ]+", "", text).strip()


def normalize_code(code: Any) -> str:
    return re.sub(r"[\s\-]", "", clean_text(code)).upper()


def extract_course_code(text: Any) -> str:
    value = clean_text(text)
    match = re.search(r"\b[A-Za-z]{2,10}[-\s]?\d{3,5}[A-Za-z]?\b", value)
    if match:
        code = match.group(0).upper().replace(" ", "-")
        if "-" not in code:
            code = re.sub(r"^([A-Z]+)(\d+.*)$", r"\1-\2", code)
        return code
    return value.upper()


def extract_codes(text: Any) -> list[str]:
    value = clean_text(text)
    if not value or value.lower() == "none":
        return []
    codes: list[str] = []
    for match in re.finditer(r"\b[A-Za-z]{2,10}[-\s]?\d{3,5}[A-Za-z]?\b", value):
        code = extract_course_code(match.group(0))
        if code and normalize_code(code) not in {normalize_code(c) for c in codes}:
            codes.append(code)
    return codes


def to_int(value: Any) -> int:
    match = re.search(r"\d+", clean_text(value))
    return int(match.group(0)) if match else 0


def term_key(term: Any) -> tuple[int, int, str]:
    value = clean_text(term).upper()
    match = re.match(r"^(\d{2,4})(SP|W|S|F)$", value)
    season_order = {"W": 0, "SP": 1, "S": 2, "F": 3}
    if not match:
        return (9999, 9, value)
    year_text, season = match.groups()
    year = int(year_text[-2:])
    return (year, season_order[season], value)


def grade_rank(grade: Any) -> tuple[int, float]:
    value = clean_text(grade).upper()
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return (3, float(value))
    letter_scores = {
        "A+": 12,
        "A": 11,
        "A-": 10,
        "B+": 9,
        "B": 8,
        "B-": 7,
        "C+": 6,
        "C": 5,
        "C-": 4,
        "D+": 3,
        "D": 2,
        "D-": 1,
        "F": 0,
    }
    if value in letter_scores:
        return (2, float(letter_scores[value]))
    if value in {"P", "PASS", "PASSED", "CR", "CREDIT"}:
        return (1, 1.0)
    return (0, 0.0)


def find_columns(headers: list[str], wanted: dict[str, list[str]]) -> dict[str, int]:
    normalized = [normalize_header(h) for h in headers]
    result: dict[str, int] = {}
    for key, needles in wanted.items():
        for index, header in enumerate(normalized):
            if any(needle in header for needle in needles):
                result[key] = index
                break
    if set(wanted).issubset(result):
        return result
    return {}


def parse_catalog_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    courses: list[dict[str, Any]] = []
    wanted = {
        "course_code": ["course code", "course"],
        "title": ["title"],
        "credits": ["credits", "credit"],
        "prerequisites": ["prerequisites", "prerequisite"],
        "cross_listed": ["cross listed", "crosslisted", "cross list"],
    }

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        columns: dict[str, int] = {}
        start = 0
        for row_index, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            headers = [cell.get_text(" ", strip=True) for cell in cells]
            columns = find_columns(headers, wanted)
            if columns:
                start = row_index + 1
                break
        if not columns:
            continue
        max_column = max(columns.values())
        for row in rows[start:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max_column:
                continue
            course_code = clean_text(cells[columns["course_code"]].get_text(" "))
            if not course_code:
                continue
            courses.append(
                {
                    "course_code": course_code,
                    "title": clean_text(cells[columns["title"]].get_text(" ")),
                    "credits": to_int(cells[columns["credits"]].get_text(" ")),
                    "prerequisites": clean_text(
                        cells[columns["prerequisites"]].get_text(" ")
                    ),
                    "cross_listed": clean_text(
                        cells[columns["cross_listed"]].get_text(" ")
                    ),
                }
            )
    return courses


def parse_transcript_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    wanted = {
        "status": ["status"],
        "course": ["course"],
        "grade": ["grade"],
        "term": ["term"],
        "credits": ["credits", "credit"],
    }
    best: dict[tuple[str, str], tuple[tuple[int, float], int, dict[str, Any]]] = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        columns: dict[str, int] = {}
        start = 0
        for row_index, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            headers = [cell.get_text(" ", strip=True) for cell in cells]
            columns = find_columns(headers, wanted)
            if columns:
                start = row_index + 1
                break
        if not columns:
            continue
        max_column = max(columns.values())
        for row in rows[start:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max_column:
                continue
            status = clean_text(cells[columns["status"]].get_text(" "))
            course_text = clean_text(cells[columns["course"]].get_text(" "))
            grade = clean_text(cells[columns["grade"]].get_text(" "))
            term = clean_text(cells[columns["term"]].get_text(" "))
            credits = to_int(cells[columns["credits"]].get_text(" "))

            if normalize_header(status) not in VALID_STATUSES:
                continue
            if not course_text or not term:
                continue
            course_code = extract_course_code(course_text)
            record = {
                "course_code": course_code,
                "term": term,
                "credits_earned": credits,
                "status": status,
            }
            key = (normalize_code(course_code), term)
            candidate = (grade_rank(grade), credits, record)
            if key not in best or (candidate[0], candidate[1]) > (
                best[key][0],
                best[key][1],
            ):
                best[key] = candidate

    records = [item[2] for item in best.values()]
    records.sort(key=lambda r: (term_key(r["term"]), normalize_code(r["course_code"])))
    return records


def require_student(student_id: str) -> dict[str, list[dict[str, Any]]]:
    if student_id not in students:
        raise HTTPException(status_code=404, detail="Student not found")
    return students[student_id]


def get_catalog_course(course_code: Any) -> dict[str, Any] | None:
    return catalog.get(normalize_code(course_code))


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/admin/catalog/import")
async def import_catalog(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    courses = parse_catalog_html(content.decode("utf-8", errors="replace"))
    catalog.clear()
    for course in courses:
        catalog[normalize_code(course["course_code"])] = course
    return {"status": "success", "imported": len(courses)}


@app.get("/api/v1/catalog/courses/{course_code}")
def get_course(course_code: str) -> dict[str, Any]:
    course = get_catalog_course(course_code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return {
        "course_code": course["course_code"],
        "title": course["title"],
        "credits": course["credits"],
        "prerequisites": course["prerequisites"],
        "cross_listed": course["cross_listed"],
    }


@app.post("/api/v1/students/{student_id}/history/import", status_code=201)
async def import_history(
    student_id: str, file: UploadFile = File(...)
) -> dict[str, Any]:
    content = await file.read()
    history = parse_transcript_html(content.decode("utf-8", errors="replace"))
    old_plan = students.get(student_id, {}).get("plan", [])
    students[student_id] = {"history": history, "plan": old_plan}
    return {"status": "success", "past_courses_imported": len(history)}


@app.put("/api/v1/students/{student_id}/history")
def update_history(student_id: str, payload: HistoryPayload) -> dict[str, str]:
    student = require_student(student_id)
    student["history"] = payload.history
    return {"status": "success", "message": "Academic history updated successfully"}


@app.delete("/api/v1/students/{student_id}/history")
def delete_history(student_id: str) -> dict[str, str]:
    student = require_student(student_id)
    student["history"] = []
    return {"status": "success", "message": "Academic history cleared successfully"}


@app.post("/api/v1/students/{student_id}/plan")
def create_plan(student_id: str, payload: PlanPayload) -> dict[str, Any]:
    student = require_student(student_id)
    student["plan"] = payload.planned_courses
    return {"status": "success", "planned_courses_saved": len(payload.planned_courses)}


@app.put("/api/v1/students/{student_id}/plan")
def update_plan(student_id: str, payload: PlanPayload) -> dict[str, Any]:
    student = require_student(student_id)
    student["plan"] = payload.planned_courses
    return {"status": "success", "planned_courses_saved": len(payload.planned_courses)}


@app.delete("/api/v1/students/{student_id}/plan")
def delete_plan(student_id: str) -> dict[str, str]:
    student = require_student(student_id)
    student["plan"] = []
    return {"status": "success", "message": "Plan cleared successfully"}


@app.get("/api/v1/students/{student_id}/profile")
def get_profile(student_id: str) -> dict[str, Any]:
    student = require_student(student_id)
    return {
        "student_id": student_id,
        "history": student["history"],
        "plan": student["plan"],
    }


def completed_by_code(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = {}
    for record in sorted(history, key=lambda r: term_key(r.get("term"))):
        if normalize_header(record.get("status", "")) != "completed":
            continue
        code = normalize_code(record.get("course_code"))
        if not code:
            continue
        completed[code] = record
    return completed


def has_completed_before(
    completed: dict[str, dict[str, Any]], prerequisite: str, planned_term: str
) -> bool:
    record = completed.get(normalize_code(prerequisite))
    if not record:
        return False
    return term_key(record.get("term")) < term_key(planned_term)


def calculate_total_earned(history: list[dict[str, Any]]) -> int:
    earned_by_course: dict[str, int] = {}
    for record in sorted(history, key=lambda r: term_key(r.get("term"))):
        if normalize_header(record.get("status", "")) != "completed":
            continue
        code = normalize_code(record.get("course_code"))
        earned_by_course[code] = max(
            int(earned_by_course.get(code, 0)), to_int(record.get("credits_earned"))
        )
    return sum(earned_by_course.values())


def calculate_total_planned(plan: list[dict[str, Any]]) -> int:
    total = 0
    for planned in plan:
        course = get_catalog_course(planned.get("course_code"))
        if course is not None:
            total += to_int(course.get("credits"))
    return total


def build_timeline_validation(
    plan: list[dict[str, Any]], completed: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for planned in plan:
        planned_code = planned.get("course_code", "")
        planned_term = clean_text(planned.get("term"))
        course = get_catalog_course(planned_code)
        if course is None:
            continue
        for prereq in extract_codes(course.get("prerequisites")):
            if not has_completed_before(completed, prereq, planned_term):
                grouped.setdefault(planned_term, []).append(
                    {
                        "course_code": planned_code,
                        "type": "MISSING_PREREQUISITE",
                        "message": f"Missing prerequisite: {prereq}",
                    }
                )
    return [
        {"term": term, "errors": grouped[term]}
        for term in sorted(grouped, key=term_key)
    ]


def build_cross_list_violations(
    plan: list[dict[str, Any]], completed: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for planned in plan:
        planned_code = planned.get("course_code", "")
        course = get_catalog_course(planned_code)
        if course is None:
            continue
        for cross_code in extract_codes(course.get("cross_listed")):
            if normalize_code(cross_code) in completed:
                violations.append(
                    {
                        "course_code": planned_code,
                        "type": "CROSS_LIST_CONFLICT",
                        "message": f"Cross-listed with completed course {cross_code}",
                    }
                )
                break
    return violations


@app.get("/api/v1/students/{student_id}/audit-report")
def audit_report(student_id: str, strict: bool = Query(False)) -> dict[str, Any]:
    student = require_student(student_id)
    history = student["history"]
    plan = student["plan"]
    completed = completed_by_code(history)

    timeline_validation = build_timeline_validation(plan, completed)
    cross_list_violations = build_cross_list_violations(plan, completed)
    total_earned = calculate_total_earned(history)
    total_planned = calculate_total_planned(plan)
    total_remaining = max(0, GRADUATION_TARGET - total_earned - total_planned)

    has_issues = bool(timeline_validation or cross_list_violations)
    if not has_issues:
        status = "ok"
    elif strict:
        status = "failed"
    else:
        status = "warning"

    return {
        "student_id": student_id,
        "status": status,
        "timeline_validation": timeline_validation,
        "cross_list_violations": cross_list_violations,
        "credit_summary": {
            "total_earned": total_earned,
            "total_planned": total_planned,
            "total_remaining_for_graduation": total_remaining,
        },
    }
