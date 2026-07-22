# Course Registration API — Phase 4

Cumulative FastAPI service implementing Phases 1–4:

- catalog import and course lookup
- per-student history, plan, profile, and audit report
- JWT registration/login with bcrypt password hashing
- BOLA protection on transcript import
- owner/admin RBAC on profile, plan lookup, and recommendations
- 10-request-per-minute sliding-window limiter on audit reports
- prerequisite-aware recommendations using Kahn's topological sort

## Local setup (Windows PowerShell)

```powershell
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set a Render environment variable named `JWT_SECRET` to a long random value.

## Submission

`api_url.txt` must contain only the deployed base URL, with no trailing slash or endpoint path.
