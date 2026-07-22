from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

CATALOG = """
<table border="1"><thead><tr>
<th>Course Code</th><th>Title</th><th>Credits</th><th>Prerequisites</th><th>Cross-listed</th>
</tr></thead><tbody>
<tr><td>COSC-4426</td><td>Capstone</td><td>3</td><td>COSC-3127</td><td></td></tr>
<tr><td>COSC-3127</td><td>Algorithms</td><td>3</td><td>None</td><td></td></tr>
<tr><td>ITEC-3506</td><td>Web Systems</td><td>3</td><td>None</td><td>COSC-3506</td></tr>
<tr><td>COSC-3506</td><td>Software Eng</td><td>3</td><td>None</td><td>ITEC-3506</td></tr>
<tr><td>COSC-2406</td><td>Data Structures</td><td>3</td><td>None</td><td></td></tr>
<tr><td>COSC-1701</td><td>Intro CS</td><td>3</td><td>None</td><td></td></tr>
<tr><td>MATH-1056</td><td>Calculus I</td><td>3</td><td>None</td><td></td></tr>
</tbody></table>
"""

TRANSCRIPT = """
<table border="1"><thead><tr>
<th>Status</th><th>Course</th><th></th><th>Grade</th><th>Term</th><th>Credits</th>
</tr></thead><tbody>
<tr><td>Attempted</td><td>COSC-1701</td><td>Intro CS</td><td>45</td><td>25F</td><td>3</td></tr>
<tr><td>Attempted</td><td>COSC-2406</td><td>Data Structures</td><td>38</td><td>25F</td><td>3</td></tr>
<tr><td>Completed</td><td>MATH-1056</td><td>Calculus I</td><td>72</td><td>25W</td><td>3</td></tr>
<tr><td>Completed</td><td>COSC-3506</td><td>Software Eng</td><td>75</td><td>26W</td><td>3</td></tr>
<tr><td>Completed</td><td>COSC-1701</td><td>Intro CS retake</td><td>68</td><td>26W</td><td>3</td></tr>
</tbody></table>
"""


def test_audit_report_warning_and_strict_failed():
    assert client.get("/").status_code == 200
    r = client.post(
        "/api/v1/admin/catalog/import",
        files={"file": ("catalog.html", CATALOG, "text/html")},
    )
    assert r.status_code == 200
    client.post(
        "/api/v1/auth/register",
        json={"username": "770001", "password": "test-pass"},
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "770001", "password": "test-pass"},
    ).json()["access_token"]
    r = client.post(
        "/api/v1/students/770001/history/import",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("student.html", TRANSCRIPT, "text/html")},
    )
    assert r.status_code == 201
    r = client.post(
        "/api/v1/students/770001/plan",
        json={
            "planned_courses": [
                {"course_code": "COSC-4426", "term": "26F"},
                {"course_code": "ITEC-3506", "term": "26F"},
                {"course_code": "COSC-2406", "term": "26F"},
            ]
        },
    )
    assert r.status_code == 200

    report = client.get("/api/v1/students/770001/audit-report").json()
    assert report["student_id"] == "770001"
    assert report["status"] == "warning"
    assert set(report) == {
        "student_id",
        "status",
        "timeline_validation",
        "cross_list_violations",
        "credit_summary",
    }
    assert report["timeline_validation"][0]["term"] == "26F"
    assert (
        report["timeline_validation"][0]["errors"][0]["type"] == "MISSING_PREREQUISITE"
    )
    assert report["cross_list_violations"][0]["type"] == "CROSS_LIST_CONFLICT"
    assert report["credit_summary"] == {
        "total_earned": 9,
        "total_planned": 9,
        "total_remaining_for_graduation": 102,
    }

    strict = client.get("/api/v1/students/770001/audit-report?strict=true").json()
    assert strict["status"] == "failed"


def test_unknown_student_is_404():
    assert client.get("/api/v1/students/never/audit-report").status_code == 404
