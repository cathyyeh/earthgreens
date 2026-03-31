# Earth Greens Realtime Dashboard v29

v29 支援：
- Render PostgreSQL
- 最後上傳檔名 / 時間顯示
- 記住上次篩選條件（localStorage）
- 保留 SQLite fallback

## 啟動
pip install -r requirements.txt
uvicorn app.main:app --reload
