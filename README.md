# Course Registration API — Phase 3

## Local run

```powershell
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload
```

## Local manual test

```powershell
curl.exe -X POST -F "file=@sample_catalog.html;type=text/html" http://127.0.0.1:8000/api/v1/admin/catalog/import
curl.exe -X POST -F "file=@student-example.html;type=text/html" http://127.0.0.1:8000/api/v1/students/770001/history/import
curl.exe -X POST http://127.0.0.1:8000/api/v1/students/770001/plan -H "Content-Type: application/json" -d "{\"planned_courses\":[{\"course_code\":\"COSC-4426\",\"term\":\"26F\"},{\"course_code\":\"ITEC-3506\",\"term\":\"26F\"},{\"course_code\":\"COSC-2406\",\"term\":\"26F\"}]}"
curl.exe http://127.0.0.1:8000/api/v1/students/770001/audit-report
curl.exe "http://127.0.0.1:8000/api/v1/students/770001/audit-report?strict=true"
```

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Phase 3 submission

Upload these files individually to VPL:

- `api_url.txt`
- `ci_proof.png` — screenshot of a green GitHub Actions run
- `ci_logs.txt` — copied text of the green GitHub Actions run logs
