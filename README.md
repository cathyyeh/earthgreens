# Earth Greens Render Deployable v30.1

Render-ready package:
- Python 3.12.8
- psycopg v3
- pandas 2.2.2
- SQLite fallback for local
- Customer analysis dashboard

Build:
pip install -r requirements.txt

Start:
uvicorn app.main:app --host 0.0.0.0 --port 10000
