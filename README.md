# Resume Tailor

A personal full-stack tool to upload, store, and tailor resumes to job descriptions.

## Stack
- **Backend**: Python + FastAPI
- **Frontend**: React + Vite

---

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend runs at: http://localhost:8000

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:3000

---

## Project Structure

```
resume-tailor/
├── backend/
│   ├── main.py           # FastAPI app
│   ├── requirements.txt
│   └── uploads/          # Saved PDFs stored here
└── frontend/
    ├── src/
    │   ├── App.jsx       # Main UI component
    │   ├── main.jsx      # React entry point
    │   └── index.css     # Global styles + design tokens
    ├── index.html
    ├── vite.config.js    # Vite + proxy config
    └── package.json
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload-resume` | Upload a PDF resume |
| `GET` | `/api/resumes` | List all saved resumes |
| `DELETE` | `/api/resumes/{filename}` | Delete a resume |

---

## Roadmap

- [x] Step 1: PDF upload + storage
- [ ] Step 2: Job description input (paste or URL)
- [ ] Step 3: AI tailoring via local Ollama
- [ ] Step 4: Download tailored PDF
