# AI Resume Tailor

An AI-powered full-stack web application that helps users tailor their resumes to specific job descriptions using Google's Gemini AI. Upload your resume, paste a job description, and get a customized resume optimized for Applicant Tracking Systems (ATS).

## ⚠️ Important Warnings

### API Key Security

- **DO NOT USE THE PROVIDED API KEY**: The `api key.txt` file contains a placeholder/example API key. You must obtain your own Google Gemini API key from [Google AI Studio](https://makersuite.google.com/app/apikey).
- **Never commit real API keys**: The `.gitignore` file excludes `api key.txt` to prevent accidental commits of sensitive information.
- Set your API key using the command in `api key.txt` (replace with your actual key) or set the environment variable `GEMINI_API_KEY`.

### ATS Resume Tailoring Status

- **WORK IN PROGRESS**: The resume ATS tailoring feature is currently **unfinished and under development**. It has only been tested and optimized for tech-based jobs. Tailoring for other job types (e.g., retail, marketing, healthcare) is not yet implemented and may produce suboptimal results.
- **Further Testing Needed**: The feature requires additional testing and refinement. Use at your own risk, and expect ongoing updates.
- **Development Continues**: This project is actively being worked on. Check for updates regularly.

## Features

- **Resume Upload**: Upload PDF resumes for processing.
- **Job Description Input**: Paste job descriptions from any source.
- **AI-Powered Tailoring**: Uses Google Gemini 2.5 Flash to analyze and tailor resumes.
- **ATS Optimization**: Attempts to optimize resumes for Applicant Tracking Systems (tech jobs only, currently).
- **Cover Letter Generation**: Generate tailored cover letters.
- **History Tracking**: View past tailoring sessions.
- **Quota Management**: Tracks Gemini API usage (free tier: 1500 requests/day).
- **File Management**: Automatic cleanup of old outputs after 14 days.

## Tech Stack

- **Backend**: Python 3.8+, FastAPI, Uvicorn
- **Frontend**: React 18, Vite
- **AI**: Google Gemini 2.5 Flash API
- **PDF Processing**: pdfplumber, ReportLab
- **Web Scraping**: BeautifulSoup4, httpx

## Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher
- A Google Gemini API key (free tier available)

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/MUmarKhan02/AI-Resume-Tailor.git
   cd AI-Resume-Tailor
   ```

2. **Backend Setup**:

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Frontend Setup**:
   ```bash
   cd ../frontend
   npm install
   ```

## Configuration

### Setting Up Your API Key

1. Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey).
2. Set the environment variable:
   - On Windows (PowerShell):
     ```powershell
     $env:GEMINI_API_KEY="your_actual_api_key_here"
     ```
   - On Linux/Mac:
     ```bash
     export GEMINI_API_KEY="your_actual_api_key_here"
     ```
3. Alternatively, create a `.env` file in the `backend/` directory with:
   ```
   GEMINI_API_KEY=your_actual_api_key_here
   ```

**WARNING**: Never commit your real API key to version control. The `.gitignore` file is set up to exclude sensitive files.

## Usage

1. **Start the Backend**:

   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

   The backend will run at http://localhost:8000

2. **Start the Frontend** (in a new terminal):

   ```bash
   cd frontend
   npm run dev
   ```

   The frontend will run at http://localhost:5173 (or similar, check the console output)

3. **Use the Application**:
   - Open the frontend URL in your browser.
   - Upload your resume PDF.
   - Paste a job description.
   - Click "Tailor Resume" to generate a customized version.
   - View history of previous tailoring sessions.

## API Endpoints

- `POST /api/upload-resume`: Upload a resume PDF
- `POST /api/tailor-resume`: Tailor resume to job description
- `GET /api/history`: Get tailoring history
- `GET /api/gemini-quota`: Check API usage quota
- `GET /api/download/{filename}`: Download generated files



## Development

- Backend uses FastAPI with automatic CORS for frontend communication.
- Frontend uses React with Vite for fast development.
- PDF processing uses pdfplumber for reading and ReportLab for writing.
- AI integration via direct HTTP calls to Gemini API.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is for educational and personal use. Please respect API usage limits and terms of service.

## Disclaimer

This tool is provided as-is. The ATS tailoring feature is experimental and may not work perfectly for all job types. Always review and customize generated content before use. The developer is not responsible for any outcomes from using this tool.

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
```
