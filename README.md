# MAPEZA ACADEMY (MACAD) — FULL SCHOOL PORTAL

## Included
- Secure password-hashed administrator login/session
- Dashboard with students, teachers, classes, fees and daily attendance
- Student register: add, search, edit, delete and individual student report
- Teacher register: add and delete
- Daily attendance: Present / Absent / Late / Excused with notes
- Fees: record transactions, balances, delete transactions
- Exams & Results: score validation, percentage calculation and delete
- Reports & analytics
- CSV exports for students and fees
- Printable individual student report
- Administrator password change
- SQLite database and downloadable database backup
- Responsive desktop/mobile interface
- MACAD logo and branding
- Health check at /health

## Windows quick start
1. Install Python 3.10 or newer.
2. Double-click `run_windows.bat`.
3. Open Microsoft Edge and visit `http://127.0.0.1:5000`.
4. Login with:
   Username: admin
   Password: admin123
5. Change the password in Settings.

## Manual start
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py

## Data
The portal creates `school.db` automatically in this folder. Use Settings > Download Database Backup regularly.

## Production
For public deployment, set a strong SECRET_KEY, use HTTPS, keep debug disabled, use a production WSGI server, and establish scheduled backups and role-based accounts.
