# MedaSync

A small hospital/clinic appointment management app built with Flask and SQLAlchemy.

## Quick start

1. Create a virtual environment and install dependencies:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

2. Run the app:

```powershell
python app.py
```

3. Open http://127.0.0.1:5000 in your browser.

Default users are created automatically on first run:
- admin / admin123
- user / user123

## Notes
- The SQLite DB is stored under `instance/hospital.db`. It is ignored by git by default to avoid committing sensitive data.
- To reset the DB, delete `instance/hospital.db` and the app will recreate it on next run.
