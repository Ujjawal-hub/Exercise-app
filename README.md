# Exercise Form Guide

Search for an exercise and see correct form, common mistakes, and images.
Backend: FastAPI · Data: wger.de API · Storage: SQLite.

## Structure

```
backend/app/main.py   FastAPI app
frontend/             static frontend (placeholder)
data/                 SQLite database lives here (git-ignored)
requirements.txt
```

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Then open http://127.0.0.1:8000 (or http://127.0.0.1:8000/docs for the API docs).
