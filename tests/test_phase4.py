from fastapi.testclient import TestClient

from main import app, rate_limit_events

client = TestClient(app)

CATALOG = """
<table><tr><th>Course Code</th><th>Title</th><th>Credits</th><th>Prerequisites</th><th>Cross-listed</th></tr>
<tr><td>COSC-1000</td><td>Intro</td><td>3</td><td>None</td><td></td></tr>
<tr><td>COSC-2000</td><td>Next</td><td>3</td><td>COSC-1000</td><td></td></tr>
<tr><td>COSC-3000</td><td>Final</td><td>3</td><td>COSC-2000</td><td></td></tr>
</table>
"""

TRANSCRIPT = """
<table><tr><th>Status</th><th>Course</th><th></th><th>Grade</th><th>Term</th><th>Credits</th></tr>
<tr><td>Completed</td><td>COSC-1000</td><td>Intro</td><td>80</td><td>25F</td><td>3</td></tr>
</table>
"""


def register_and_login(username: str, password: str = "pw123456") -> str:
    response = client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code in {201, 409}
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_auth_bola_rbac_recommendations_and_rate_limit():
    student_token = register_and_login("12345")
    other_token = register_and_login("99999")
    admin = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    ).json()["access_token"]

    assert client.post(
        "/api/v1/admin/catalog/import",
        files={"file": ("catalog.html", CATALOG, "text/html")},
    ).status_code == 200

    assert client.post(
        "/api/v1/students/12345/history/import",
        headers=auth(student_token),
        files={"file": ("student.html", TRANSCRIPT, "text/html")},
    ).status_code == 201
    assert client.post(
        "/api/v1/students/12345/history/import",
        headers=auth(other_token),
        files={"file": ("student.html", TRANSCRIPT, "text/html")},
    ).status_code == 401
    assert client.post(
        "/api/v1/students/12345/history/import",
        files={"file": ("student.html", TRANSCRIPT, "text/html")},
    ).status_code == 401

    assert client.get("/api/v1/students/12345/profile").status_code == 401
    assert client.get(
        "/api/v1/students/12345/profile", headers=auth(other_token)
    ).status_code == 401
    assert client.get(
        "/api/v1/students/12345/profile", headers=auth(student_token)
    ).status_code == 200
    assert client.get(
        "/api/v1/students/12345/profile", headers=auth(admin)
    ).status_code == 200

    recommendation = client.get(
        "/api/v1/students/12345/recommendations", headers=auth(student_token)
    )
    assert recommendation.status_code == 200
    pathway = recommendation.json()["recommended_pathway"]
    flattened = [course for term in pathway for course in term["courses"]]
    assert "COSC-1000" not in flattened
    assert flattened.index("COSC-2000") < flattened.index("COSC-3000")

    rate_limit_events.clear()
    statuses = [
        client.get(
            "/api/v1/students/12345/audit-report", headers=auth(student_token)
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
