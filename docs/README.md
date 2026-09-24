# Setup Guide - AI Timetable Scheduler

## Quick Setup (3 Steps)

### 1. Database Setup
```bash
mysql -u root -p < database/schema.sql
```

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your MySQL password
python init_db.py
uvicorn app.main:app --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Default Login
- Username: `admin`
- Password: `admin123`

## URLs
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs

For detailed instructions, see README.md
