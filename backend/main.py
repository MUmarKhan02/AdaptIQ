from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import hmac
import hashlib
import base64
from contextlib import asynccontextmanager
import shutil
import os
import re
import json
import asyncio
from time import perf_counter
from collections import Counter
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
import pdfplumber


from dotenv import load_dotenv
load_dotenv()
# ── Auth ──────────────────────────────────────────────────────────────────────
_AUTH_PASSWORD     = os.environ.get("ADAPTIQ_PASSWORD", "changeme")
_AUTH_SECRET       = os.environ.get("ADAPTIQ_SECRET",   "adaptiq-secret-key-change-me")
_TOKEN_EXPIRY_DAYS = 30
_UNPROTECTED_PATHS = {"/", "/api/auth/login", "/api/gemini-quota"}
_UNPROTECTED_PREFIXES = ("/api/download/", "/api/download-cl/")

def _sign_token(payload: str) -> str:
    sig = hmac.new(_AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()

def _verify_token(token: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit(".", 1)
        expected = hmac.new(_AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return datetime.utcnow() < datetime.fromisoformat(payload)
    except Exception:
        return False

def _make_token() -> str:
    expiry = (datetime.utcnow() + timedelta(days=_TOKEN_EXPIRY_DAYS)).isoformat()
    return _sign_token(expiry)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_purge_loop())
    yield

app = FastAPI(title="AdaptIQ API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in _UNPROTECTED_PATHS:
        return await call_next(request)
    if any(path.startswith(p) for p in _UNPROTECTED_PREFIXES):
        return await call_next(request)
    if path.startswith("/api/"):
        token = request.headers.get("X-Auth-Token") or request.cookies.get("adaptiq_token")
        if not token or not _verify_token(token):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

UPLOAD_DIR    = Path("uploads")
OUTPUT_DIR    = Path("outputs")
OUTPUT_CL_DIR = Path("output_cl")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_CL_DIR.mkdir(exist_ok=True)

# ── Output retention ───────────────────────────────────────────────────────
OUTPUT_TTL_DAYS = 14

def purge_old_outputs():
    """Delete any output PDF older than OUTPUT_TTL_DAYS days."""
    cutoff = datetime.now() - timedelta(days=OUTPUT_TTL_DAYS)
    removed = []
    for folder in [OUTPUT_DIR, OUTPUT_CL_DIR]:
        for f in folder.glob("*.pdf"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed.append(f.name)
    if removed:
        print(f"[purge] Removed {len(removed)} expired output(s): {removed}")
    return removed

async def _purge_loop():
    """Background task: purge once on startup then every hour."""
    while True:
        purge_old_outputs()
        await asyncio.sleep(3600)


def as_str(value) -> str:
    return str(value or "").strip()


def normalize_list_of_strings(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    cleaned = []
    for item in values:
        if item is None:
            continue
        item_text = str(item or "").strip()
        if item_text:
            cleaned.append(item_text)
    return cleaned


def validate_bullet_repetition(resume_data: dict) -> None:
    """
    Detect repeated meaningful words in bullets and log warnings.
    No Gemini calls — pure Python only.

    Intentionally SKIPS bullets where the repetition is a legitimate
    compound proper noun or tech name (e.g. "Spring Boot, Spring Security",
    "Graph-CNN", "CNN+LSTM") because AI was mangling those cases and the
    repetition is not actually a writing problem.
    """
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "can", "shall", "this", "that", "these",
        "those", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
        "my", "your", "his", "its", "our", "their", "what", "which", "who", "when", "where", "why",
        "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "just", "now",
        # Common resume/tech verbs that repeat innocuously
        "using", "based", "via", "per", "into", "from", "across", "between",
    }

    # Words that legitimately repeat as parts of different proper nouns/tech names.
    # e.g. "Spring Boot, Spring Security" — "spring" repeats but both are valid names.
    COMPOUND_WHITELIST = {
        "spring", "next", "node", "graph", "cnn", "lstm", "net", "js",
        "data", "web", "base", "end", "api", "rest", "type", "react",
        "boot", "cloud", "fast", "deep", "open", "micro", "test",
    }

    for section in resume_data.get("sections", []):
        for entry in section.get("entries", []):
            for bullet in normalize_list_of_strings(entry.get("bullets")):
                words = re.findall(r"\b\w+\b", bullet.lower())
                meaningful = [w for w in words if len(w) >= 3 and w not in stopwords]
                repeated = [w for w, c in Counter(meaningful).items() if c > 1]
                # Filter out whitelisted compound-name words
                real_repeats = [w for w in repeated if w not in COMPOUND_WHITELIST]
                if real_repeats:
                    print(f"WARNING: Bullet contains repeated words: {real_repeats} in '{bullet}'")

# Get your free API key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_URL     = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

# ── Gemini quota tracker (in-memory, resets at midnight) ──────────────────
# Gemini 2.5 Flash free tier: 1500 requests/day, 10 RPM
GEMINI_DAILY_LIMIT = 1500
GEMINI_RPM_LIMIT   = 10

_quota = {
    "date":         datetime.now().date(),
    "used":         0,
    "minute_calls": [],  # timestamps of calls in the last 60 seconds
}

def _quota_reset_if_new_day():
    today = datetime.now().date()
    if _quota["date"] != today:
        _quota["date"] = today
        _quota["used"] = 0

def quota_increment():
    _quota_reset_if_new_day()
    _quota["used"] += 1
    now = datetime.now()
    _quota["minute_calls"].append(now)
    cutoff = now - timedelta(seconds=60)
    _quota["minute_calls"] = [t for t in _quota["minute_calls"] if t > cutoff]

def quota_snapshot() -> dict:
    _quota_reset_if_new_day()
    now       = datetime.now()
    used      = _quota["used"]
    remaining = max(0, GEMINI_DAILY_LIMIT - used)
    midnight  = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    secs_left = int((midnight - now).total_seconds())
    # RPM
    cutoff = now - timedelta(seconds=60)
    _quota["minute_calls"] = [t for t in _quota["minute_calls"] if t > cutoff]
    rpm_used      = len(_quota["minute_calls"])
    rpm_remaining = max(0, GEMINI_RPM_LIMIT - rpm_used)
    if _quota["minute_calls"]:
        oldest      = min(_quota["minute_calls"])
        rpm_reset_s = max(0, int(60 - (now - oldest).total_seconds()) + 1)
    else:
        rpm_reset_s = 0
    return {
        "used":          used,
        "remaining":     remaining,
        "limit":         GEMINI_DAILY_LIMIT,
        "resets_in_s":   secs_left,
        "resets_at":     midnight.isoformat(),
        "rpm_used":      rpm_used,
        "rpm_remaining": rpm_remaining,
        "rpm_limit":     GEMINI_RPM_LIMIT,
        "rpm_reset_s":   rpm_reset_s,
    }

@app.get("/api/gemini-quota")
def get_gemini_quota():
    return quota_snapshot()

JOB_BOARD_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "greenhouse.io",
    "lever.co", "workday.com", "myworkdayjobs.com", "icims.com",
    "jobvite.com", "smartrecruiters.com", "taleo.net", "brassring.com",
    "careers.google.com", "jobs.apple.com", "amazon.jobs", "microsoft.com",
    "careers.microsoft.com", "metacareers.com", "jobs.netflix.com",
    "boards.greenhouse.io", "jobs.lever.co", "apply.workable.com",
    "wellfound.com", "angellist.com", "ziprecruiter.com", "monster.com",
    "careerbuilder.com", "dice.com", "simplyhired.com", "hired.com",
    "weworkremotely.com", "remoteok.com", "ycombinator.com", "jobleads.com",
}

JOB_PATH_KEYWORDS = [
    "job", "jobs", "career", "careers", "position", "opening",
    "vacancy", "vacancies", "hiring", "apply", "application",
    "recruit", "talent", "opportunity", "role",
]

JOB_CONTENT_KEYWORDS = [
    "responsibilities", "requirements", "qualifications", "experience",
    "skills", "salary", "benefits", "apply now", "job description",
    "about the role", "about the position", "what you'll do",
    "what we're looking for", "who you are", "compensation",
]

BLOCKED_DOMAINS = {
    "youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "reddit.com", "tiktok.com", "twitch.tv", "netflix.com",
    "spotify.com", "pinterest.com", "wikipedia.org", "amazon.com",
    "ebay.com", "craigslist.org", "yelp.com", "tripadvisor.com",
}

# ATS-standard section title mappings
ATS_SECTION_MAP = {
    "work experience":         "EXPERIENCE",
    "professional experience": "EXPERIENCE",
    "employment history":      "EXPERIENCE",
    "work history":            "EXPERIENCE",
    "relevant experience":     "EXPERIENCE",
    "experience":              "EXPERIENCE",
    "educational background":  "EDUCATION",
    "academic background":     "EDUCATION",
    "education":               "EDUCATION",
    "technical skills":        "TECHNICAL SKILLS",
    "core skills":             "TECHNICAL SKILLS",
    "skills & technologies":   "TECHNICAL SKILLS",
    "skills and technologies": "TECHNICAL SKILLS",
    "technologies":            "TECHNICAL SKILLS",
    "skills":                  "TECHNICAL SKILLS",
    "tools & technologies":    "TECHNICAL SKILLS",
    "personal projects":       "PROJECTS",
    "side projects":           "PROJECTS",
    "projects":                "PROJECTS",
    "key projects":            "PROJECTS",
    "professional summary":    "SUMMARY",
    "profile":                 "SUMMARY",
    "objective":               "SUMMARY",
    "about me":                "SUMMARY",
    "summary":                 "SUMMARY",
    "certifications & awards": "CERTIFICATIONS",
    "certificates":            "CERTIFICATIONS",
    "awards":                  "CERTIFICATIONS",
    "certifications":          "CERTIFICATIONS",
    "achievements":            "CERTIFICATIONS",
    "publications":            "PUBLICATIONS",
    "research":                "PUBLICATIONS",
    "volunteer experience":    "VOLUNTEER EXPERIENCE",
    "volunteering":            "VOLUNTEER EXPERIENCE",
    "community":               "VOLUNTEER EXPERIENCE",
    "languages":               "LANGUAGES",
}


def normalize_section_title(title: str) -> str:
    key = title.strip().lower()
    return ATS_SECTION_MAP.get(key, title.strip().upper())


def is_likely_job_url(url: str, html: str, title: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")
    path   = parsed.path.lower()

    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return False, f"This looks like a {domain} link, not a job posting."

    for job_domain in JOB_BOARD_DOMAINS:
        if domain == job_domain or domain.endswith("." + job_domain):
            return True, "Recognized job board."

    path_hit      = any(kw in path for kw in JOB_PATH_KEYWORDS)
    content_lower = html.lower()
    content_hits  = sum(1 for kw in JOB_CONTENT_KEYWORDS if kw in content_lower)

    if path_hit and content_hits >= 2:
        return True, "Job posting detected."
    if content_hits >= 4:
        return True, "Job posting detected."
    if path_hit:
        return True, "Possible job posting."

    return False, "This URL doesn't appear to be a job posting. Please paste a direct link to a job listing."


def extract_job_body(soup: BeautifulSoup) -> str:
    """Extract job description text from a parsed HTML page.
    
    Strategy:
    1. Try JSON-LD structured data (JobPosting schema) — server-rendered even on
       JS-heavy sites like RBC, LinkedIn, Greenhouse. Most reliable.
    2. Try known CSS selectors for job description containers.
    3. Fall back to full page text.
    """
    import json as _json

    # ── Strategy 1: JSON-LD JobPosting schema ────────────────────────────────
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script_tag.string or "")
            # Handle both single objects and arrays
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "JobPosting"), None)
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                parts = []
                if data.get("title"):
                    parts.append(data["title"])
                if data.get("description"):
                    # Strip HTML tags from the description field
                    desc_soup = BeautifulSoup(data["description"], "html.parser")
                    parts.append(desc_soup.get_text(separator=" ", strip=True))
                if data.get("qualifications"):
                    parts.append(data["qualifications"])
                if data.get("responsibilities"):
                    parts.append(data["responsibilities"])
                if data.get("skills"):
                    parts.append(str(data["skills"]))
                combined = " ".join(parts).strip()
                if len(combined) > 300:
                    combined = re.sub(r"\s{2,}", " ", combined)
                    return combined[:6000]
        except Exception:
            continue

    # ── Strategy 2: CSS selectors ────────────────────────────────────────────
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "noscript", "iframe", "form"]):
        tag.decompose()

    candidate_selectors = [
        "[class*='job-description']", "[class*='jobDescription']",
        "[class*='job-content']",     "[class*='jobContent']",
        "[class*='description']",     "[id*='job-description']",
        "[id*='jobDescription']",     "[class*='posting']",
        "[class*='job-detail']",      "article", "main",
    ]
    body_text = ""
    for sel in candidate_selectors:
        el = soup.select_one(sel)
        if el:
            body_text = el.get_text(separator=" ", strip=True)
            if len(body_text) > 300:
                break

    # ── Strategy 3: full page text ───────────────────────────────────────────
    if not body_text:
        body_text = soup.get_text(separator=" ", strip=True)

    body_text = re.sub(r"\s{2,}", " ", body_text).strip()
    return body_text[:6000]


MIN_JOB_BODY_LENGTH = 400  # chars — below this the page is likely JS-rendered or expired

def assess_body_quality(body_text: str) -> tuple[bool, str]:
    """Check if scraped body text is rich enough to extract meaningful keywords.
    Returns (is_good_enough, user_facing_message)."""
    if len(body_text) < MIN_JOB_BODY_LENGTH:
        return False, (
            "The job page didn't return enough content — it may require JavaScript to load "
            "(common on RBC, Workday, and some LinkedIn pages). "
            "Please copy and paste the full job description text instead."
        )
    # Check for job-like vocabulary — at least a few role-relevant words
    job_vocab = ["experience", "skills", "responsibilities", "qualifications",
                 "requirements", "role", "position", "team", "develop", "manage"]
    hits = sum(1 for w in job_vocab if w in body_text.lower())
    if hits < 2:
        return False, (
            "The page content doesn't look like a job description. "
            "Please paste the job description text directly."
        )
    return True, ""


@app.get("/")
def root():
    return {"message": "AdaptIQ API is running"}

@app.post("/api/auth/login")
async def login(payload: dict):
    password = payload.get("password", "")
    if not hmac.compare_digest(password, _AUTH_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = _make_token()
    return {"token": token, "expires_days": _TOKEN_EXPIRY_DAYS}

@app.post("/api/auth/logout")
async def logout():
    return {"ok": True}


@app.post("/api/fetch-job-url")
async def fetch_job_url(payload: dict):
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided.")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Please enter a valid URL starting with http:// or https://")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="The page took too long to load. Try again.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Could not access that URL (HTTP {e.response.status_code}).")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not reach that URL. Check the link and try again.")

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or \
                soup.find("meta", attrs={"property": "og:description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    is_job, reason = is_likely_job_url(url, html, title)
    if not is_job:
        raise HTTPException(status_code=422, detail=reason)

    body_text = extract_job_body(soup)

    is_good, quality_msg = assess_body_quality(body_text)
    if not is_good:
        raise HTTPException(status_code=422, detail=quality_msg)

    return {
        "success":     True,
        "url":         str(response.url),
        "title":       title,
        "description": description,
        "body_text":   body_text,
    }


@app.post("/api/tailor-resume")
async def tailor_resume(payload: dict):
    """Tailor a resume and return the result as JSON."""
    try:
        resume_filename = payload.get("resume_filename", "").strip()
        job_text        = payload.get("job_text", "").strip()

        if not resume_filename or not job_text:
            raise HTTPException(status_code=400, detail="Missing resume filename or job content.")

        if not GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set.")

        resume_path = UPLOAD_DIR / resume_filename
        if not resume_path.exists():
            raise HTTPException(status_code=404, detail="Resume file not found.")

        try:
            resume_text = ""
            hyperlinks  = {}
            with pdfplumber.open(resume_path) as pdf:
                original_page_count = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        resume_text += text + "\n"
                    if page.annots:
                        for annot in page.annots:
                            uri = annot.get("uri") or annot.get("URI")
                            if not uri:
                                continue
                            uri_lower = uri.lower()
                            if "mailto:" in uri_lower:
                                label = "Email"
                            elif "linkedin.com" in uri_lower:
                                label = "LinkedIn"
                            elif "github" in uri_lower and ".io" in uri_lower and "github.com" not in uri_lower:
                                label = "Portfolio"
                            elif "github.com" in uri_lower:
                                label = "GitHub"
                            else:
                                label = "Portfolio"
                            hyperlinks[label] = uri
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not read PDF: {str(e)}")

        if not resume_text.strip():
            raise HTTPException(status_code=500, detail="Could not extract text from the resume PDF.")

        def extract_plain_section_bullets(section_title: str, text: str) -> list[str]:
            """Extract bullets from a plain-bullet section.

            Handles two layouts produced by pdfplumber:
            1. SUMMARY — wrapped prose: join continuation lines into one paragraph.
            2. SKILLS SUMMARY — two items per physical line separated by ' • ':
               e.g. '• Item A • Item B'  →  ['Item A', 'Item B']
               Also handles wrapped items like:
               '• Microsoft Excel (sorting, filtering, formulas, data • Attention to detail'
               'validation) • Inventory awareness'
               →  ['Microsoft Excel (sorting, filtering, formulas, data validation)', 'Attention to detail', 'Inventory awareness']
            """
            lines = [line.rstrip() for line in text.splitlines()]
            title_norm = section_title.strip().upper()
            is_summary_section    = "SUMMARY" in title_norm and "SKILL" not in title_norm
            is_skills_summary     = "SKILLS" in title_norm and "SUMMARY" in title_norm
            raw_lines: list[str] = []
            collecting = False
            blank_count = 0

            for line in lines:
                stripped = line.strip()
                if collecting:
                    if not stripped:
                        blank_count += 1
                        if blank_count >= 2:
                            break
                        continue
                    blank_count = 0
                    if len(stripped) >= 4 and stripped == stripped.upper() and re.match(r"^[A-Z][A-Z0-9 &/\-]+$", stripped):
                        break
                    raw_lines.append(stripped)
                elif stripped.upper() == title_norm:
                    collecting = True

            if not raw_lines:
                return []

            # ── SKILLS SUMMARY: interleaved "• left • right" layout ────────────
            if is_skills_summary:
                # Step 1: join physical continuation lines (lines not starting with •)
                joined: list[str] = []
                for raw in raw_lines:
                    if not raw.lstrip().startswith("•") and joined:
                        joined[-1] = joined[-1].rstrip() + " " + raw.strip()
                    else:
                        joined.append(raw)

                # Step 2: parse each joined line with a paren-aware • splitter.
                # Handles the edge case where the two-column layout places a column
                # separator • inside an open paren, e.g.:
                # "• Excel (sorting, data • Attention to detail validation) • Inventory"
                # → ["Excel (sorting, data validation)", "Attention to detail", "Inventory"]
                def _parse_skills_line(ln: str) -> list[str]:
                    ln = re.sub(r"^\s*•\s*", "", ln)
                    result_parts: list[str] = []
                    ln_depth = 0
                    ln_current: list[str] = []
                    ki = 0
                    while ki < len(ln):
                        ch = ln[ki]
                        if ch == "(":
                            ln_depth += 1
                            ln_current.append(ch)
                            ki += 1
                        elif ch == ")":
                            ln_depth = max(0, ln_depth - 1)
                            ln_current.append(ch)
                            ki += 1
                        elif ch == "•":
                            if ln_depth == 0:
                                chunk = "".join(ln_current).strip()
                                if chunk:
                                    result_parts.append(chunk)
                                ln_current = []
                                ki += 1
                                while ki < len(ln) and ln[ki] == " ":
                                    ki += 1
                            else:
                                # Trapped • inside open paren — column separator artifact.
                                # Scan to matching ')'; split content into:
                                #   closing_word  → belongs to left item's paren list
                                #   right_item    → is the right-column skill
                                ki += 1
                                while ki < len(ln) and ln[ki] == " ":
                                    ki += 1
                                between: list[str] = []
                                while ki < len(ln) and ln[ki] != ")":
                                    between.append(ln[ki])
                                    ki += 1
                                ki += 1  # skip the ')'
                                ln_depth = max(0, ln_depth - 1)
                                bw_words = "".join(between).strip().split()
                                closing_word = bw_words[-1] if bw_words else ""
                                right_item   = " ".join(bw_words[:-1]) if len(bw_words) >= 2 else ""
                                if closing_word:
                                    ln_current.append(" ")
                                    ln_current.extend(list(closing_word))
                                ln_current.append(")")
                                left = re.sub(r"  +", " ", "".join(ln_current).strip())
                                if left:
                                    result_parts.append(left)
                                ln_current = []
                                if right_item:
                                    result_parts.append(right_item.strip())
                                while ki < len(ln) and ln[ki] == " ":
                                    ki += 1
                        else:
                            ln_current.append(ch)
                            ki += 1
                    tail_part = "".join(ln_current).strip()
                    if tail_part:
                        result_parts.append(tail_part)
                    return result_parts

                items: list[str] = []
                for joined_line in joined:
                    items.extend(_parse_skills_line(joined_line))
                return [it for it in items if it.strip()]

            # ── SUMMARY: join wrapped prose lines ─────────────────────────────
            captured: list[str] = []
            for raw in raw_lines:
                stripped = raw.strip()
                clean = re.sub(r"^[\u2022\u2023\u25E6\-\*]\s*", "", stripped).strip()
                clean = re.sub(r"^•\s*", "", clean).strip()
                if not clean:
                    continue
                is_bullet_start = bool(re.match(r"^[•\-\*]", stripped))
                if is_summary_section and captured and not is_bullet_start:
                    captured[-1] = captured[-1].rstrip() + " " + clean
                else:
                    captured.append(clean)
            return [line for line in captured if line.strip()]

        original_skills_summary_bullets = extract_plain_section_bullets("SKILLS SUMMARY", resume_text)
        original_summary_bullets = extract_plain_section_bullets("SUMMARY", resume_text)

        def extract_original_bullets_from_resume(text: str) -> dict[str, list[str]]:
            """Extract all bullets from EXPERIENCE and PROJECTS, joining pypdf-wrapped lines.
            Returns { "EXPERIENCE": [bullet1, bullet2, ...], "PROJECTS": [...] }
            """
            BULLET_RE     = re.compile(r"^[•‣◦●●▸●•\-\*]\s+")
            SECTION_HEADER = re.compile(r"^[A-Z][A-Z0-9 &/\-]{3,}$")
            # Lines that look like an experience entry heading (job title + date glued on by pypdf)
            ENTRY_HEADING_RE = re.compile(r".{4,}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}")
            TARGET_SECTIONS = {"EXPERIENCE", "PROJECTS", "VOLUNTEER", "VOLUNTEER EXPERIENCE"}

            result: dict[str, list[str]] = {}
            lines = [l.rstrip() for l in text.splitlines()]
            current_section: str | None = None
            current_bullet: list[str] = []
            pool: list[str] = []

            # Heading-like patterns pypdf glues onto the end of the last bullet
            HEADING_SUFFIX = re.compile(
                r"\.\s+("
                r"[A-Z][a-zA-Z ]+ \| "          # "Blog Platform | ..."
                r"|University of [A-Z]"           # "University of Windsor..."
                r"|Wayne State"
                r"|[A-Z]{2,}[a-z]* [A-Z][a-z]+"  # "Teaching Assistant", "Research Assistant"
                r")",
                re.IGNORECASE,
            )

            def flush_bullet():
                if current_bullet:
                    full = " ".join(current_bullet).strip()
                    # Truncate at any point where a heading got glued on by pypdf
                    m = HEADING_SUFFIX.search(full)
                    if m:
                        full = full[:m.start() + 1].strip()  # keep the period, drop the rest
                    if full:
                        pool.append(full)
                    current_bullet.clear()

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if SECTION_HEADER.match(stripped):
                    header = stripped.upper()
                    if header in TARGET_SECTIONS:
                        flush_bullet()
                        if current_section and pool:
                            result[current_section] = list(pool)
                            pool.clear()
                        current_section = header
                    elif current_section:
                        flush_bullet()
                        if pool:
                            result[current_section] = list(pool)
                            pool.clear()
                        current_section = None
                    continue
                if current_section is None:
                    continue
                if BULLET_RE.match(stripped):
                    flush_bullet()
                    current_bullet.append(BULLET_RE.sub("", stripped).strip())
                elif current_bullet and ENTRY_HEADING_RE.match(stripped):
                    # pypdf glued a "Job Title Month YYYY" line onto the last bullet — flush now, don't append
                    flush_bullet()
                else:
                    if current_bullet:
                        current_bullet.append(stripped)

            flush_bullet()
            if current_section and pool:
                result[current_section] = list(pool)
            return result

        original_section_bullets = extract_original_bullets_from_resume(resume_text)

        import asyncio

        class RateLimitError(Exception):
            def __init__(self, retry_after: int):
                self.retry_after = retry_after
                super().__init__(f"Rate limit hit — retry in {retry_after}s")

        async def call_gemini(prompt: str, temperature: float = 0.1, max_tokens: int = 1024) -> str:
            """Call Gemini API. Fails immediately on 429 — retries up to 3x on transient 5xx errors."""
            for attempt in range(3):
                attempt_start = perf_counter()
                print(f"[call_gemini] attempt={attempt+1}/2 temperature={temperature} max_tokens={max_tokens} starting")
                try:
                    async with httpx.AsyncClient(timeout=120) as client:
                        resp = await client.post(
                            GEMINI_URL,
                            headers={"Content-Type": "application/json"},
                            json={
                                "contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {
                                    "temperature":     temperature,
                                    "maxOutputTokens": max_tokens,
                                    "thinkingConfig":  {"thinkingBudget": 0},
                                },
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            raise ValueError("No candidates in response")
                        parts = candidates[0].get("content", {}).get("parts", [])
                        elapsed = perf_counter() - attempt_start
                        print(f"[call_gemini] attempt={attempt+1} succeeded elapsed={elapsed:.1f}s status={resp.status_code} candidates={len(candidates)}")
                        quota_increment()
                        return "".join(p.get("text", "") for p in parts).strip()
                except httpx.ConnectError:
                    elapsed = perf_counter() - attempt_start
                    print(f"[call_gemini] attempt={attempt+1} connect error elapsed={elapsed:.1f}s")
                    raise Exception("Could not reach Gemini API.")
                except httpx.HTTPStatusError as e:
                    elapsed = perf_counter() - attempt_start
                    retry_after_hdr = e.response.headers.get("retry-after")
                    print(f"[call_gemini] attempt={attempt+1} http error elapsed={elapsed:.1f}s status={e.response.status_code} retry_after={retry_after_hdr}")
                    if e.response.status_code == 403:
                        raise Exception("Invalid GEMINI_API_KEY.")
                    if e.response.status_code == 429:
                        retry_after = int(retry_after_hdr) if retry_after_hdr else 60
                        print(f"[call_gemini] rate limited — failing immediately, retry in {retry_after}s")
                        raise RateLimitError(retry_after)
                    if e.response.status_code in (500, 502, 503, 504):
                        wait = 3 * (attempt + 1)  # 3s, 6s, 9s
                        print(f"[call_gemini] transient {e.response.status_code} — waiting {wait}s before retry")
                        if attempt == 2:
                            raise Exception("Gemini service unavailable. Please try again in a moment.")
                        await asyncio.sleep(wait)
                        continue
                    raise Exception(f"Gemini API error {e.response.status_code}")
                except RateLimitError:
                    raise
                except Exception as e:
                    elapsed = perf_counter() - attempt_start
                    print(f"[call_gemini] attempt={attempt+1} failed elapsed={elapsed:.1f}s error={e}")
                    if "Could not reach" in str(e) or "Invalid GEMINI" in str(e):
                        raise
                    if attempt == 2:
                        raise Exception(f"AI call failed: {str(e)}")
                    await asyncio.sleep(2)
            raise Exception("Request failed after 3 attempts.")

        print("[tailor_resume] stage=start single_pass_rewrite")

        def parse_json_response(raw: str) -> dict:
            clean = raw.strip()
            clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE)
            clean = clean.strip()
            start = clean.index("{")
            end   = clean.rindex("}") + 1
            return json.loads(clean[start:end])

        # Single-pass prompt: keyword extraction + resume rewrite in one Gemini call.
        # Previously two separate calls (keyword extraction then rewrite); merging them
        # eliminates one RPM unit and avoids rate-limit exposure.
        prompt = f"""You are an expert ATS resume writer. Your task has two parts — do both together and return a single JSON object.

PART A — KEYWORD ANALYSIS (from the job description):
Identify internally and include in the output JSON:
  - tier1_hard_skills: specific named TECHNICAL hard skills EXPLICITLY mentioned in the job description (languages, frameworks, tools, platforms, named software). Extract ONLY what appears in the text. Maximum 12 items. Technical only — no soft skills here.
  - tier2_professional_concepts: concise NON-TECHNICAL workplace skill phrases (2-5 words) matching this role's domain — e.g. task estimation, code review, clear communication, defined requirements, on-time delivery. Extract only what the job description actually emphasizes. Maximum 8 items. Soft/process only — never put tool names here.
  - exclude_from_bullets: skills or tools that would be factually inaccurate for this candidate based on the resume (e.g. if JD requires PHP but candidate has never used it, exclude PHP from bullet injection).
CRITICAL: Base ALL extraction purely on what the job description explicitly says. The role domain determines what keywords are relevant. Never mix domains.
Use these keywords when rewriting bullets in Part B.

PART B — RESUME REWRITE:
Rewrite the resume below to pass ATS screening for the given job description using the keywords you identified.

RULES — follow every one exactly:

RULE 1 — PRESERVE ALL CONTENT:
Keep every section, every entry, and every bullet. Never drop, merge, omit, shorten, or reorder anything.
CRITICAL: Every bullet must be at LEAST as long as the original. If the original bullet is "Coordinated with a team of guards to maintain safety protocols and respond to incidents promptly", the output must contain the full sentence — never "Coordinated with a team of guards" alone. Truncating the end of a bullet is a critical failure.
When in doubt: copy the bullet verbatim, then add the keyword injection. Never remove words that were already there.

RULE 2 — PRESERVE ALL NUMBERS EXACTLY:
Copy all numbers, percentages, dataset sizes, and counts character-for-character.
e.g. "530k+ entry dataset", "~75%", "30 epochs", "100+ students" must appear unchanged.

RULE 3 — KEYWORD INJECTION — HOW TO DO IT RIGHT:
Your goal is to weave keywords into bullets by replacing vague words with more specific ones from the keyword list, or by restructuring the sentence so the keyword is part of the core action — not tacked on at the end.

TIERED INJECTION RULES:
- Tier 1 keywords (hard technical skills / named tools): Only inject these if they already appear somewhere in the original resume. If a Tier 1 keyword does not appear in the original resume, do not inject it anywhere.
- Tier 2 keywords (professional concepts / soft skills): Always inject these wherever they fit naturally. For non-technical resumes (customer service, admin, warehouse, hospitality), Tier 2 is your PRIMARY injection target — these are exactly the keywords ATS systems scan for in soft-skill roles.
- CRITICAL — NO PRECISION DOWNGRADE: If a bullet already contains a specific, accurate term, NEVER replace it with a vaguer one.

RESUME TYPE DETECTION:
If the resume contains a "SKILLS SUMMARY" section with plain bullet soft skills (rather than a "TECHNICAL SKILLS" section with Category: tool lists), treat it as a NON-TECHNICAL RESUME. For non-technical resumes:
  - Tier 2 injection into experience bullets is the main goal
  - Replace vague action verbs or generic descriptions with the exact phrasing from the JD
  - Weave in concepts like "data accuracy", "data integrity", "confidentiality", "reporting", "attention to detail" naturally into bullets that already demonstrate those things

CONCRETE EXAMPLES — TECHNICAL resume:

  ORIGINAL:  "Implemented a RAG pipeline with TF-IDF chunk retrieval, reducing context window usage"
  REWRITTEN: "Implemented an NLP retrieval pipeline using RAG with TF-IDF chunk scoring, reducing context window usage and improving response relevance"
  WHY VALID: "NLP retrieval pipeline" replaces "RAG pipeline" — the keyword enriches the description of what was built.

CONCRETE EXAMPLES — NON-TECHNICAL resume:

  ORIGINAL:  "Managed and organized large datasets and documentation as part of a university research project"
  REWRITTEN: "Maintained data accuracy and completeness across large datasets and documentation as part of a university research project"
  WHY VALID: "data accuracy and completeness" replaces "organized" — directly matches JD language for a data entry role.

  ORIGINAL:  "Collaborated with a team to test and evaluate multiple solutions, tracking results and recommending the best approach"
  REWRITTEN: "Collaborated with a team to evaluate multiple solutions, tracking results and identifying data discrepancies to recommend the best approach"
  WHY VALID: "identifying data discrepancies" slots naturally into the existing structure and matches JD requirement.

WHAT IS FORBIDDEN — appending phrases to already-complete sentences:
  ORIGINAL:  "Optimized throughput by ~75% using ThreadPoolExecutor, with real-time SSE streaming."
  FORBIDDEN: "Optimized throughput by ~75% using ThreadPoolExecutor, with real-time SSE streaming, for machine learning research."
  FORBIDDEN: Repeating any word or acronym already used earlier in the same bullet
  FORBIDDEN: Do not inject the same keyword across more than 2 bullets in the entire resume.
  WHY BAD:   The sentence was complete. You just bolted words onto the end. This is keyword stuffing.

THE RULE: if you can remove your addition and the sentence still makes complete sense on its own, your addition is forbidden. Rewrite the whole sentence instead, or leave it as-is.

If a keyword truly cannot fit naturally into any bullet, leave it out.

RULE 4 — DO NOT USE BANNED KEYWORDS IN BULLETS:
Never inject any keyword from your exclude_from_bullets list into any bullet.

RULE 5 — SKILLS SECTION:
  - Treat the skills section as read-only content.
  - Copy every skill category and every item exactly as they appear in the original resume.
  - Do not remove, add, or reorder any skill unless the job posting mentions a skill already present in the category, in which case you may move that existing item earlier within its current category.
  - Do not add any new skills unless the candidate clearly demonstrates them in an original project or experience bullet.
  - Format: "Category: tool1, tool2, tool3"

RULE 5A — PLAIN BULLET SECTIONS:
  - If a section contains plain bullets with no "Category:" prefix, treat every bullet as read-only.
  - Copy each bullet exactly as it appears in the original resume into the output.
  - Do not rewrite, paraphrase, shorten, omit, or inject keywords into those bullets.
  - If a section is titled "SKILLS SUMMARY" or contains plain bullet points without a "Category:" prefix, preserve all bullets verbatim in the output unchanged. Do not summarize, omit, or rewrite any of those bullets.

RULE 5B — SUMMARY SECTION:
  - Copy the SUMMARY section VERBATIM from the original resume. Every word, every sentence, character-for-character.
  - Do NOT change anything. No keyword injection, no rephrasing, no reordering.
  - If there is no SUMMARY section in the original resume, do not create one.
RULE 6 — NO MARKDOWN:
No bold, no italic, no backticks, no bullet symbols. Plain text only in every field.

RULE 7 — SECTION TITLES:
Keep section titles exactly as they appear in the original resume. Do not change or normalize them.

RULE 8 — ENTRY FORMAT:
  Education:  heading = "School | City, State | Start – End", subheading = "Degree · GPA", bullets = []
  Experience: heading = "Job Title", subheading = "Company | City, State | Start – End", bullets = rewritten bullets
  Projects:   heading = "Project Name", subheading = "tech stack only", bullets = rewritten bullets

RULE 9 — NO INVENTED CONTENT:
Every bullet must trace to an original bullet. Never invent tools, achievements, or responsibilities.

RULE 10 — CONTACT LINE:
Copy the contact line EXACTLY as it appears in the original resume, including any pipe characters (|), symbols, or formatting.

RULE 11 — OUTPUT:
Return ONLY valid JSON. No markdown fences, no text before or after.
Include your Part A keyword analysis as top-level fields alongside the resume data.

{{
  "name": "full name",
  "contact": "contact line exactly as original including all | symbols",
  "tier1_hard_skills": ["tool1", "tool2"],
  "tier2_professional_concepts": ["phrase1", "phrase2"],
  "exclude_from_bullets": ["phrase1"],
  "sections": [
    {{
      "title": "SECTION TITLE",
      "entries": [
    {{
      "heading": "per rule 8",
      "subheading": "per rule 8",
      "bullets": ["bullet 1", "bullet 2"]
    }}
      ]
    }}
  ]
}}

RULE 12 — NO WORD REPETITION:
Never use the same meaningful word, noun, or acronym more than once within a single bullet. Before finalizing each bullet, scan it for repeated terms and rewrite the sentence to eliminate them. This applies to acronyms too — e.g. never write 'NLP pipeline for NLP understanding'.
If an acronym or meaningful word appears twice, rewrite the entire bullet so the concept appears only once; do not simply remove one duplicate instance.
For example, do not write: "Designed NLP pipeline for NLP understanding." Rewrite it as: "Designed an NLP pipeline to improve understanding."
EXCEPTION: Do NOT treat compound proper nouns as repetitions. "Spring Boot, Spring Security" is two distinct product names — do not alter them. "Graph-CNN" contains "CNN" but is one name — do not alter it.

CONCRETE EXAMPLE — Keyword Injection Causing Repetition:
  ORIGINAL: "Developed a system for text analysis"
  FORBIDDEN: "Developed an NLP system for NLP text analysis" (NLP appears twice after injecting the keyword)
  CORRECT:  "Developed an NLP system to enhance text analysis performance" (restructured whole sentence so NLP appears exactly once)

RULE 13 — LENGTH CONSTRAINT:
Keep each rewritten bullet equal to or shorter in character length than the original bullet. If a rewrite exceeds the original length, trim it down while preserving keyword injection and core meaning. The goal is to keep the overall resume the same length as the original.

ORIGINAL RESUME:
{resume_text}

JOB DESCRIPTION:
{job_text}

JSON:"""

        raw = await call_gemini(prompt, temperature=0.25, max_tokens=8500)

        try:
            resume_data = parse_json_response(raw)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {str(e)}")

        # Extract keyword fields from merged response (Part A output)
        tier1_keywords     = resume_data.pop("tier1_hard_skills", [])
        tier2_keywords = resume_data.pop("tier2_professional_concepts", [])
        excluded_kws    = resume_data.pop("exclude_from_bullets", [])
        excluded_str    = ", ".join(excluded_kws) if excluded_kws else "none"

        resume_data["hyperlinks"] = hyperlinks

        # ── Fix name doubling
        name_in_data = resume_data.get("name", "").strip()
        contact_in_data = resume_data.get("contact", "").strip()
        if name_in_data and contact_in_data.startswith(name_in_data):
            resume_data["contact"] = contact_in_data[len(name_in_data):].lstrip(" |,").strip()

        # ─────────────────────────────────────────────────────────────────────────
        # Post-process helpers
        # ─────────────────────────────────────────────────────────────────────────
        APPEND_PATTERNS = [
            r",?\s+for\s+(machine learning|ML|NLP|AI|safety|research)\s*(research|applications?|purposes?|tasks?)?\.?$",
            r",?\s+to\s+(publish|evaluate|support|demonstrate|contribute to)\s+[\w\s]+\.?$",
            r",?\s+supporting\s+[\w\s]+(pipeline|training|evaluation|research)s?\.?$",
            r",?\s+demonstrating\s+[\w\s]+(skills?|applications?|capabilities?)\.?$",
            r",?\s+contributing\s+to\s+[\w\s]+(pipeline|research|evaluation)s?\.?$",
            r",?\s+in\s+(ML|NLP|AI|machine learning)\s+applications?\.?$",
            r",?\s+for\s+(NLP\s+)?document\s+understanding\.?$",
            r"\s+to\s+(build|drive|write|solve|design|create|develop|deliver)\s+[\w\s,]+\.?$",
            r"\s+to\s+maintain\s+[\w\s]+\.?$",
            r"\s+to\s+improve\s+[\w\s]+\.?$",
            r"\s+and\s+ensure\s+[\w\s]+\.?$",
            r"\s+to\s+support\s+[\w\s]+\.?$",
            r"\s+for\s+[\w\s]+\s+development\.?$",
        ]

        VAGUE_TERMS = {
            "machine learning", "deep learning", "artificial intelligence", "ai",
            "data analysis", "data science", "software development", "web development",
            "utilized", "utilizing", "leveraged", "applied", "used", "techniques", "management",
            "development", "analysis", "modeling", "workflows", "efficient", "learning",
        }

        def strip_markdown(text: str) -> str:
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            text = re.sub(r"\*(.+?)\*",     r"\1", text)
            text = re.sub(r"`(.+?)`",       r"\1", text)
            text = re.sub(r"^[•\-\*]\s*",   "",    text.strip())
            return text.strip()

        def strip_appended_phrases(bullet: str) -> str:
            for pattern in APPEND_PATTERNS:
                bullet = re.sub(pattern, "", bullet, flags=re.IGNORECASE).strip()
            bullet = re.sub(r",\s*$", "", bullet).strip()
            return bullet

        # Post-process 1: Clean all text fields
        for section in resume_data.get("sections", []):
            is_skills = "SKILL" in section.get("title", "").upper()
            for entry in section.get("entries", []):
                cleaned = []
                for b in normalize_list_of_strings(entry.get("bullets")):
                    if not b:
                        continue
                    b = strip_markdown(b)
                    if not is_skills:
                        b = strip_appended_phrases(b)
                    if b:
                        cleaned.append(b)
                entry["bullets"]    = cleaned
                entry["heading"]    = strip_markdown(as_str(entry.get("heading")))
                entry["subheading"] = strip_markdown(as_str(entry.get("subheading")))

        # Post-process 2: Preserve original skills section
        original_skill_lines: dict[str, str] = {}
        original_skill_order: list[str] = []

        NON_SKILL_PREFIXES = {
            "email", "phone", "tel", "address", "linkedin", "github",
            "portfolio", "website", "url", "name", "gpa", "university",
            "college", "school", "location", "city",
        }

        _last_skill_cat: str | None = None
        for line in resume_text.splitlines():
            stripped = line.strip()
            if not stripped:
                _last_skill_cat = None
                continue
            m = re.match(r"^([A-Za-z0-9 &/+-]+):\s*(.+)$", stripped)
            if m:
                cat_key = m.group(1).strip().lower()
                if cat_key in NON_SKILL_PREFIXES:
                    _last_skill_cat = None
                    continue
                if cat_key not in original_skill_lines:
                    original_skill_lines[cat_key] = m.group(2).strip()
                    original_skill_order.append(m.group(1).strip())
                    _last_skill_cat = cat_key
                else:
                    _last_skill_cat = None
            elif _last_skill_cat and re.match(r"^[A-Za-z0-9]", stripped):
                # Continuation line — pypdf wrapped a long skill list onto the next line.
                # Only join if it still looks like a comma-separated skill list fragment.
                # Reject if it looks like an institution, date range, job title, or section header.
                _is_section_header   = bool(re.match(r"^[A-Z][A-Z0-9 &/\-]{3,}$", stripped))
                _has_pipe            = "|" in stripped
                _has_year            = bool(re.search(r"\b(19|20)\d{2}\b", stripped))
                _has_month_range     = bool(re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", stripped))
                _looks_like_sentence = len(stripped.split()) > 6 and "," not in stripped
                # Must look like a skill fragment: has a comma (multiple items) OR is a
                # short tech token (digits/dots/symbols allowed, <=3 plain words).
                # Blocks plain English phrases like "Research Assistant" or "Teaching Assistant".
                _has_comma      = "," in stripped
                _has_tech_char  = bool(re.search(r"[0-9.#+/()\-]", stripped))
                _is_single_word = len(stripped.split()) == 1
                _is_skill_token = bool(re.match(r"^[A-Za-z0-9.][A-Za-z0-9 .#+/()\-]*$", stripped)) and (_is_single_word or _has_tech_char)
                _looks_like_skill = _has_comma or _is_skill_token
                if _looks_like_skill and not any([_is_section_header, _has_pipe, _has_year, _has_month_range, _looks_like_sentence]):
                    original_skill_lines[_last_skill_cat] = original_skill_lines[_last_skill_cat].rstrip(", ") + ", " + stripped.rstrip(",")
            else:
                _last_skill_cat = None

        def split_skill_items(skill_line: str) -> list[str]:
            """Split a comma-separated skill line into items.
            Treats parenthetical groups as atomic — commas inside (...) are not split points.
            e.g. "Git, AWS (Elastic Beanstalk, RDS, S3), Docker" → ["Git", "AWS (Elastic Beanstalk, RDS, S3)", "Docker"]
            """
            items = []
            current = []
            depth = 0
            for ch in skill_line:
                if ch == "(":
                    depth += 1
                    current.append(ch)
                elif ch == ")":
                    depth -= 1
                    current.append(ch)
                elif ch == "," and depth == 0:
                    token = "".join(current).strip()
                    if token:
                        items.append(token)
                    current = []
                else:
                    current.append(ch)
            token = "".join(current).strip()
            if token:
                items.append(token)
            return items

        def reorder_existing_items(items: list[str], keywords: list[str]) -> list[str]:
            matched = []
            rest = []
            for item in items:
                item_lower = item.lower()
                if any(kw in item_lower for kw in keywords):
                    matched.append(item)
                else:
                    rest.append(item)
            ordered = []
            seen = set()
            for item in items:
                if item in matched and item not in seen:
                    ordered.append(item)
                    seen.add(item)
            for item in items:
                if item not in seen:
                    ordered.append(item)
            return ordered

        # Skills that must never be injected into any category
        SKILL_BLOCKLIST = {
            "threadpoolexecutor", "ollama", "llama 3.2", "llama3.2", "llama",
            "claude ai", "claude", "gpt", "openai", "gemini", "mistral",
            "duckduckgo", "sse", "k-means", "apriori", "graph-cnn",
            "euclidean-distance clustering", "euclidean", "snowflake",
        }

        def _is_injectable_skill(skill: str) -> bool:
            sl = skill.strip().lower()
            if sl in SKILL_BLOCKLIST:
                return False
            # Block action phrases (job-description soft language)
            if any(sl.startswith(v) for v in [
                "build", "write", "solve", "drive", "collect", "synthesize",
                "design", "contribute", "process", "demonstrate", "apply",
                "scope", "collaborat", "seek", "find",
            ]):
                return False
            # Block anything longer than 3 words
            if len(skill.strip().split()) > 3:
                return False
            # Block algorithm / method descriptions
            if any(p in sl for p in [
                "clustering", "algorithm", "distance", "segmentation",
                "classification", "regression", "detection",
            ]):
                return False
            return True

        def choose_skill_category(skill: str) -> str | None:
            if not _is_injectable_skill(skill):
                return None
            skill_lower = skill.lower().strip()

            # Block soft/process concepts — they have no place in a technical skills section
            non_tech_signals = [
                "communication", "ownership", "delivery", "estimation", "review",
                "collaboration", "planning", "management", "agile", "scrum",
                "workflow", "feedback", "mentorship", "leadership",
            ]
            if any(sig in skill_lower for sig in non_tech_signals):
                return None

            # Explicit skill-type taxonomy to prevent misrouting.
            # e.g. Laravel must never land in Languages; Vue must never land in Frameworks.
            LANGUAGES = {
                "php", "python", "java", "javascript", "typescript", "c", "c#", "c++",
                "ruby", "go", "rust", "swift", "kotlin", "scala", "r", "sql", "bash",
                "shell", "perl", "dart", "elixir", "haskell", "lua",
            }
            FRAMEWORKS = {
                "laravel", "symfony", "codeigniter", "django", "flask", "fastapi",
                "rails", "spring", "spring boot", "express", "nest.js", "nestjs",
                "asp.net", "next.js", "nuxt", "nuxt.js", "gatsby",
            }
            FRONTEND_FW = {
                "vue", "vue.js", "react", "angular", "svelte", "alpine.js",
                "htmx", "jquery", "backbone.js",
            }
            DATABASES = {
                "mysql", "postgresql", "postgres", "sqlite", "mongodb", "redis",
                "snowflake", "mariadb", "oracle", "mssql", "dynamodb", "cassandra",
                "firebase", "supabase",
            }

            for cat_display in original_skill_order:
                cat_key = cat_display.lower()

                if cat_key == "languages":
                    # Pure programming/query languages only — never frameworks
                    if skill_lower in LANGUAGES and skill_lower not in FRAMEWORKS and skill_lower not in FRONTEND_FW:
                        return cat_display
                    continue

                if any(k in cat_key for k in ["framework", "library", "libraries"]):
                    if skill_lower in FRAMEWORKS:
                        return cat_display
                    continue

                if any(k in cat_key for k in ["frontend", "front-end", "front end"]):
                    if skill_lower in FRONTEND_FW:
                        return cat_display
                    continue

                if any(k in cat_key for k in ["database", "db"]):
                    if skill_lower in DATABASES:
                        return cat_display
                    continue

                if any(k in cat_key for k in ["tool", "devops", "platform", "service"]):
                    # Catch-all for tooling — only if not already categorized above
                    if skill_lower not in LANGUAGES and skill_lower not in FRAMEWORKS and skill_lower not in FRONTEND_FW and skill_lower not in DATABASES:
                        return cat_display
                    continue

                if any(k in cat_key for k in ["data", "ai", "ml", "analytics", "machine learning"]):
                    return cat_display

            # No suitable category found — don't inject
            return None

        skill_keywords = [kw.lower() for kw in tier1_keywords if kw.strip()]
        skill_items_per_cat: dict[str, list[str]] = {
            cat_display: split_skill_items(original_skill_lines[cat_display.lower()])
            for cat_display in original_skill_order
        }

        for cat_display, items in skill_items_per_cat.items():
            skill_items_per_cat[cat_display] = reorder_existing_items(items, skill_keywords)

        resume_lower = resume_text.lower()
        # Inject Tier 1 skills — ONLY if the skill already appears in the original resume body.
        # Never fabricate or infer. If it's not there, it does not get added.
        for skill in tier1_keywords:
            if not skill.strip():
                continue
            skill_lower = skill.lower()
            already_present = any(
                skill_lower == item.lower() or skill_lower in item.lower()
                for items in skill_items_per_cat.values()
                for item in items
            )
            if already_present:
                continue
            if re.search(rf"(?<!\w){re.escape(skill_lower)}(?!\w)", resume_lower):
                target_cat = choose_skill_category(skill)
                if target_cat and skill not in skill_items_per_cat.get(target_cat, []):
                    skill_items_per_cat[target_cat].append(skill)
                    print(f"[skills] Injected '{skill}' into '{target_cat}' (found in resume body)")

        final_skill_lines: list[str] = [
            f"{cat_display}: {', '.join(skill_items_per_cat[cat_display])}"
            for cat_display in original_skill_order
        ]

        for section in resume_data.get("sections", []):
            title_upper = section.get("title", "").upper()
            if "SKILL" in title_upper:
                if "SKILLS SUMMARY" in title_upper or "SKILL SUMMARY" in title_upper:
                    # Start from original bullets — AI must not modify plain-bullet skill sections
                    base_bullets = list(original_skills_summary_bullets) if original_skills_summary_bullets else [
                        b for entry in section.get("entries", [])
                        for b in normalize_list_of_strings(entry.get("bullets"))
                    ]
                    # Inject tier 2 soft skills from the JD that aren't already present.
                    # Only add if genuinely absent — case-insensitive check.
                    base_lower = [b.lower() for b in base_bullets]
                    injected_count = 0
                    MAX_SOFT_INJECTIONS = 5
                    for kw in tier2_keywords:
                        if injected_count >= MAX_SOFT_INJECTIONS:
                            break
                        kw_lower = kw.lower().strip()
                        if not kw_lower:
                            continue
                        # Dedup check 1: exact or substring match
                        already_exact = any(kw_lower in b for b in base_lower)
                        # Dedup check 2: significant word overlap — if 2+ meaningful words
                        # of the new keyword already appear in any existing skill, skip it.
                        # e.g. "communication skills" overlaps "customer service & communication"
                        # Strong domain words — if any of these appear in both the
                        # new keyword AND an existing skill, treat as duplicate.
                        STRONG_SKILL_WORDS = {
                            "communication", "teamwork", "customer", "service",
                            "inventory", "data", "problem", "solving",
                            "time", "detail", "leadership", "organization", "entry",
                            "reliability", "collaboration", "initiative", "typing",
                        }
                        kw_words = {w for w in kw_lower.split() if len(w) > 3}
                        kw_strong = kw_words & STRONG_SKILL_WORDS
                        already_overlap = any(
                            # Block if: 2+ word overlap, OR any single strong-domain word matches
                            len(kw_words & {w for w in b.split() if len(w) > 3}) >= min(2, len(kw_words))
                            or bool(kw_strong & {w for w in b.split()})
                            for b in base_lower
                        ) if kw_words else False
                        if not already_exact and not already_overlap:
                            kw_titled = kw.title()
                            base_bullets.append(kw_titled)
                            base_lower.append(kw_lower)
                            injected_count += 1
                            print(f"[skills summary] Injected tier2 soft skill: '{kw_titled}'")
                        else:
                            print(f"[skills summary] Skipped duplicate: '{kw}' (overlaps existing)")
                    section["entries"] = [{"heading": "", "subheading": "", "bullets": base_bullets}]
                    continue
                # Regular categorized skills section
                section["entries"] = [{"heading": "", "subheading": "", "bullets": final_skill_lines}]
                break

        # ── Summary rewrite — focused, honest refocusing ────────────────────────
        # Rewrites the summary to lead with what this specific JD cares about,
        # without fabricating any new claims. Falls back to original if anything goes wrong.

        # Detect resume type here too — needed for summary rewrite framing.
        # (Also computed again in scoring block below — that's intentional, keep both.)
        is_non_tech_resume = bool(original_skills_summary_bullets)

        original_summary_text = " ".join(original_summary_bullets).strip() if original_summary_bullets else ""
        tailored_summary_text = original_summary_text  # default: keep original

        if original_summary_text and job_text.strip():
            try:
                resume_type_hint = (
                    "This is a NON-TECHNICAL resume (customer service / admin / general labour). "
                    "The summary should lead with the most relevant soft skills and availability for this role."
                    if is_non_tech_resume else
                    "This is a TECHNICAL resume (software engineering / development). "
                    "The summary should lead with the most relevant technical specialisation for this role."
                )
                summary_prompt = f"""You are rewriting a resume summary to better match a specific job description.

RESUME TYPE: {resume_type_hint}

ORIGINAL SUMMARY:
{original_summary_text}

JOB DESCRIPTION (first 1500 chars):
{job_text[:1500]}

RULES — follow every one exactly:
1. Keep the same length (± 10 words). Do not make it longer.
2. Do not add any claim, skill, technology, or experience not already present in the original summary.
3. Only reorder, refocus, or rephrase existing content to lead with what the JD emphasises.
4. Keep the same person and tense (first/third person, present/past).
5. For technical resumes: if the JD emphasises a specific stack or domain (e.g. backend, ML, cloud), lead with that angle from what's already in the summary.
6. For non-technical resumes: lead with the most relevant soft skill or availability statement for this role.
7. If the original summary already matches the JD well, return it unchanged.
8. Return ONLY the rewritten summary text — no labels, no JSON, no explanation.

REWRITTEN SUMMARY:"""

                candidate = await call_gemini(summary_prompt, temperature=0.2, max_tokens=300)
                candidate = candidate.strip()
                # Validate: must be non-empty, not too different in length, no JSON artifacts
                if (candidate and
                    len(candidate) > 30 and
                    len(candidate) < len(original_summary_text) * 2.5 and
                    "{" not in candidate and
                    "REWRITTEN" not in candidate.upper()):
                    tailored_summary_text = candidate
                    print(f"[summary] Rewritten ({len(original_summary_text)} → {len(tailored_summary_text)} chars)")
                else:
                    print(f"[summary] Rewrite rejected, keeping original")
            except Exception as e:
                print(f"[summary] Rewrite failed ({e}), keeping original")

        for section in resume_data.get("sections", []):
            title_upper = section.get("title", "").upper()
            if title_upper == "SUMMARY" and original_summary_text:
                section["entries"] = [{"heading": "", "subheading": "", "bullets": [tailored_summary_text]}]

        # Post-process 3: Drop empty bullets
        for section in resume_data.get("sections", []):
            for entry in section.get("entries", []):
                entry["bullets"] = normalize_list_of_strings(entry.get("bullets"))

        # Post-process 4: Restore original bullets for EXPERIENCE and PROJECTS
        # Gemini keeps heading/subheading/structure; bullet text always comes from original PDF.
        # Uses a flat pool matched by count per entry — immune to truncation and stuffing.
        for section in resume_data.get("sections", []):
            title_upper = section.get("title", "").upper()
            orig_key = None
            if "VOLUNTEER" in title_upper:
                orig_key = "VOLUNTEER"
            elif "VOLUNTEER EXPERIENCE" in title_upper:
                orig_key = "VOLUNTEER EXPERIENCE"
            elif "EXPERIENCE" in title_upper:
                orig_key = "EXPERIENCE"
            elif "PROJECT" in title_upper:
                orig_key = "PROJECTS"
            if not orig_key or orig_key not in original_section_bullets:
                continue
            orig_pool = original_section_bullets[orig_key]
            pool_idx  = 0
            for entry in section.get("entries", []):
                ai_count = len(normalize_list_of_strings(entry.get("bullets")))
                if ai_count == 0 or pool_idx >= len(orig_pool):
                    continue
                entry["bullets"] = orig_pool[pool_idx: pool_idx + ai_count]
                pool_idx += ai_count



        def extract_keyword_fallback_scan(text: str) -> tuple[list[str], list[str]]:
            lower_text = text.lower()
            stopwords = {
                "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
                "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do",
                "does", "did", "will", "would", "could", "should", "may", "might", "can", "shall",
                "this", "that", "these", "those", "it", "its", "we", "they", "their", "what", "which",
                "who", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more",
                "most", "other", "some", "such", "no", "not", "only", "same", "so", "than", "too",
                "very", "job", "role", "position", "experience", "requirements", "responsibilities",
                "skills", "working", "work", "team", "candidate", "applicant", "application",
                "including", "using", "use", "used", "required", "preferred", "ability", "abilities",
                "company", "organization", "organizations", "business", "management", "support",
                "service", "services", "department", "departments", "customer", "customers",
            }

            words = re.findall(r"\b[a-z0-9][a-z0-9\-']*\b", lower_text)
            tokens = [w for w in words if w not in stopwords and len(w) > 1]
            if not tokens:
                return [], []

            phrase_counts = Counter(
                " ".join(tokens[i:i+n])
                for n in (3, 2)
                for i in range(len(tokens) - n + 1)
            )
            repeated_phrases = [phrase for phrase, cnt in phrase_counts.items() if cnt > 1]

            word_counts = Counter(tokens)
            repeated_words = [word for word, cnt in word_counts.items() if cnt > 1]

            fallback = []
            for phrase in sorted(repeated_phrases, key=lambda p: (-len(p.split()), -phrase_counts[p], p)):
                if phrase not in fallback:
                    fallback.append(phrase)
                    if len(fallback) >= 15:
                        break
            for word in sorted(repeated_words, key=lambda w: (-word_counts[w], w)):
                if word not in fallback:
                    fallback.append(word)
                    if len(fallback) >= 15:
                        break

            return [], fallback[:15]

        # tier1_keywords and tier2_keywords already extracted from main Gemini response above
        all_kw_lower: set[str] = {kw.strip().lower() for kw in tier1_keywords + tier2_keywords if kw.strip()}

        validate_bullet_repetition(resume_data)

        # Extract company and role with regex — no Gemini call needed.
        # Extract company and role via Gemini for reliability
        async def extract_company_role(text: str) -> tuple[str, str]:
            prompt = (
                "Extract the company name and job title from this job description.\n"
                'Return ONLY a JSON object with exactly two fields, no markdown:\n'
                '{"company": "company name", "role": "job title"}\n\n'
                f"JOB DESCRIPTION:\n{text[:2000]}\n\nJSON:"
            )
            try:
                raw = await call_gemini(prompt, temperature=0.0, max_tokens=128)
                clean = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
                si = clean.index("{")
                ei = clean.rindex("}") + 1
                extracted = json.loads(clean[si:ei])
                company = str(extracted.get("company", "")).strip()[:50]
                role    = str(extracted.get("role",    "")).strip()[:60]
                return company, role
            except Exception as e:
                print(f"extract_company_role failed: {e}")
                return "", ""

        company, role = await extract_company_role(job_text)
        company_role = f"{company}-{role}" if company and role else (company or role or "Unknown")
        company_role = re.sub(r'[<>:"/\\|?*]', '', company_role).strip()


        now_time = datetime.now()
        date_str        = now_time.strftime("%Y%m%d")
        time_str        = now_time.strftime("%H%M%S")
        stem            = Path(resume_filename).stem
        author = resume_data.get("name", "").strip() or stem
        author = re.sub(r'[<>:"/\\|?*]', '', author).strip()
        output_filename = f"{author}-{company_role}-Resume-{date_str}_{time_str}.pdf"
        output_path     = OUTPUT_DIR / output_filename

        try:
            _build_resume_pdf(resume_data, str(output_path))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

        with pdfplumber.open(str(output_path)) as pdf:
            new_page_count = len(pdf.pages)
        if new_page_count > original_page_count:
            all_bullets = []
            for section in resume_data.get("sections", []):
                for entry in section.get("entries", []):
                    for bullet in normalize_list_of_strings(entry.get("bullets")):
                        all_bullets.append((len(bullet), bullet))
            all_bullets.sort(reverse=True)
            longest = all_bullets[:5]
            print(f"WARNING: PDF page count increased from {original_page_count} to {new_page_count}. Longest bullets:")
            for length, bullet in longest:
                print(f"  {length} chars: {bullet}")

        gen_cover          = payload.get("gen_cover", False)
        cover_filename_out = None

        if gen_cover:

            cover_filename_out = await _generate_cover_letter(
                resume_text=resume_text,
                hyperlinks=hyperlinks,
                job_text=job_text,
                stem=stem,
                date_str=date_str,
                time_str=time_str,
                candidate_name=resume_data.get("name", ""),
                company_role=company_role,
            )

        def _calculate_quantification_rate(data: dict) -> tuple[int, int, int]:
            metric_pattern = re.compile(
                r"\b\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?\+?%?\b|\b\d+(?:[kKmM])\+?\b|\b\d+\s*(?:years?|months?|weeks?|days?|hours?|minutes?|seconds?|secs?|epochs?|samples?|records?|users?|customers?|students?|researchers?)\b",
                re.IGNORECASE,
            )
            bullets = []
            for section in data.get("sections", []):
                for entry in section.get("entries", []):
                    bullets.extend(normalize_list_of_strings(entry.get("bullets")))

            total = len(bullets)
            quantified = sum(1 for b in bullets if metric_pattern.search(b))
            rate = round((quantified / total) * 100) if total else 0
            return quantified, total, rate

        quantified_bullets, total_bullets, quantification_rate = _calculate_quantification_rate(resume_data)

        # ── Keyword coverage: scan actual tailored resume text for JD keyword presence
        def normalize_text_for_matching(text: str) -> str:
            normalized = re.sub(r"[^a-z0-9\s]+", " ", text.lower())
            return re.sub(r"\s+", " ", normalized).strip()

        all_resume_text = " ".join(
            part
            for section in resume_data.get("sections", [])
            for entry in section.get("entries", [])
            for part in (
                normalize_list_of_strings(entry.get("bullets"))
                + [as_str(entry.get("heading")), as_str(entry.get("subheading"))]
            )
        )
        normalized_resume_text = normalize_text_for_matching(all_resume_text)
        normalized_original_text = normalize_text_for_matching(resume_text)

        def keyword_present(keyword: str, text: str) -> bool:
            keyword = keyword.strip().lower()
            if not keyword:
                return False
            escaped = re.escape(keyword)
            escaped = escaped.replace(r"\ ", r"\s+")
            return re.search(rf"(?<!\w){escaped}(?!\w)", text, flags=re.IGNORECASE) is not None

        # ── Synonym/alias map: if a JD keyword matches any alias, treat it as present
        SKILL_SYNONYMS = [
            # REST / API variations
            {"rest api", "rest apis", "restful api", "restful apis", "restful", "rest"},
            # SQL variants
            {"sql", "sql server", "microsoft sql server", "t-sql", "tsql", "mssql"},
            # Cloud / AWS
            {"aws", "amazon web services", "amazon aws"},
            {"elastic beanstalk", "aws elastic beanstalk"},
            {"ec2", "aws ec2", "amazon ec2"},
            {"s3", "aws s3", "amazon s3"},
            {"lambda", "aws lambda"},
            # Azure
            {"azure", "microsoft azure", "ms azure"},
            # GCP
            {"gcp", "google cloud", "google cloud platform"},
            # Kubernetes / container
            {"kubernetes", "k8s"},
            {"docker", "docker container", "docker containers"},
            # CI/CD
            {"ci/cd", "ci cd", "continuous integration", "continuous deployment", "continuous delivery"},
            # JavaScript variants
            {"javascript", "js"},
            {"typescript", "ts"},
            {"node.js", "nodejs", "node js"},
            # React
            {"react", "react.js", "reactjs"},
            # Python
            {"python", "python3", "python 3"},
            # C++ / C
            {"c++", "cpp", "c plus plus"},
            # Machine learning
            {"machine learning", "ml"},
            {"artificial intelligence", "ai"},
            {"natural language processing", "nlp"},
            # Data / analytics
            {"power bi", "powerbi"},
            {"tableau", "tableau software"},
            # Version control
            {"git", "github", "gitlab", "git/github"},
            # Linux / Unix
            {"linux", "unix", "unix/linux", "linux/unix"},
            # Agile
            {"agile", "agile methodology", "agile methodologies", "scrum", "agile/scrum"},
            # OOP
            {"oop", "object oriented programming", "object-oriented programming", "object oriented", "object-oriented"},
            # Spring
            {"spring", "spring boot", "spring framework"},
            # Microservices
            {"microservices", "microservice", "microservice architecture", "microservices architecture"},
            # Shell
            {"shell", "shell script", "shell scripting", "bash", "bash scripting"},
            # JWT
            {"jwt", "jwt authentication", "json web token", "json web tokens"},
            # PostgreSQL
            {"postgresql", "postgres"},
            # MongoDB
            {"mongodb", "mongo"},
            # Java build tools
            {"maven", "apache maven"},
            {"gradle", "apache gradle"},
            # .NET
            {".net", "dotnet", "asp.net", "asp.net core"},
            # Testing
            {"junit", "junit5", "junit 5"},
            # Redis
            {"redis", "redis cache"},
        ]

        def _get_synonym_group(keyword: str):
            kw = keyword.strip().lower()
            for group in SKILL_SYNONYMS:
                if kw in group:
                    return group
            return {kw}

        def keyword_present_with_synonyms(keyword: str, text: str) -> bool:
            """Check if keyword OR any of its synonyms appear in text."""
            for alias in _get_synonym_group(keyword):
                if keyword_present(alias, text):
                    return True
            return False

        # ── Detect resume type: non-tech resumes use SKILLS SUMMARY (plain bullets),
        # tech resumes use TECHNICAL SKILLS (Category: item lists).
        # This changes what drives the coverage score:
        #   Tech:     tier1 hard skills coverage (are the required tools in the resume?)
        #   Non-tech: tier2 soft skill coverage (are the required concepts demonstrated?)
        # is_non_tech_resume already set above before summary rewrite — reused here for scoring
        # is_non_tech_resume = bool(original_skills_summary_bullets)

        tier1_injectable      = [kw for kw in tier1_keywords if keyword_present_with_synonyms(kw, normalized_original_text)]
        tier1_gap             = [kw for kw in tier1_keywords if not keyword_present_with_synonyms(kw, normalized_original_text)]
        tier1_matched         = [kw for kw in tier1_injectable if keyword_present_with_synonyms(kw, normalized_resume_text)]
        injected_keyword_list = [kw for kw in tier1_keywords
                                 if keyword_present_with_synonyms(kw, normalized_resume_text)
                                 and not keyword_present_with_synonyms(kw, normalized_original_text)]

        if is_non_tech_resume:
            # Non-tech: tier1 + tier2 combined.
            # Tier1 captures real tools (Excel, Office 365, POS systems).
            # Tier2 captures soft skill concepts (fast-paced, customer service, etc).
            # Both matter for non-tech ATS scoring.
            tier2_matched       = [kw for kw in tier2_keywords if keyword_present_with_synonyms(kw, normalized_resume_text)]
            tier2_gap           = [kw for kw in tier2_keywords if not keyword_present_with_synonyms(kw, normalized_resume_text)]
            keyword_match_count = len(tier1_matched) + len(tier2_matched)
            keyword_total_count = len(tier1_injectable) + len(tier2_keywords)
        else:
            # Tech: tier1 only — hard skills are the only meaningful signal.
            tier2_matched = []
            tier2_gap     = []
            keyword_match_count = len(tier1_matched)
            keyword_total_count = len(tier1_injectable)
        keyword_injection_count = len(injected_keyword_list)

        tier1_injectable      = list(dict.fromkeys(tier1_injectable))
        tier1_gap             = list(dict.fromkeys(tier1_gap))
        tier1_matched         = list(dict.fromkeys(tier1_matched))
        injected_keyword_list = list(dict.fromkeys(injected_keyword_list))

        # ── Final event (100%)

        # Return final result
        final_result = {
            "success":               True,
            "output_filename":       output_filename,
            "cover_letter_filename": cover_filename_out,
            "scoring": {
                "tier1_keywords":           tier1_keywords,
                "tier2_keywords":           tier2_keywords,
                "excluded_kws":             excluded_kws,
                "keyword_injection_count":  keyword_injection_count,
                "job_text_length":          len(job_text),
                "quantified_bullets":       quantified_bullets,
                "total_bullets":            total_bullets,
                "quantification_rate":      quantification_rate,
                "matched_keywords":         keyword_match_count,
                "total_keywords":           keyword_total_count,
                "tier1_injectable":         tier1_injectable,
                "tier1_gap":                tier1_gap,
                "tier1_matched":            tier1_matched,
                "tier2_matched":            tier2_matched,
                "tier2_gap":                tier2_gap,
                "is_non_tech_resume":       is_non_tech_resume,
                "injected_keywords":        injected_keyword_list,
            }
        }

        return final_result



    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e)
        if "Rate limit hit" in err_str:
            import re as _re
            m = _re.search(r'retry in (\d+)s', err_str)
            retry_secs = int(m.group(1)) if m else 60
            print(f"[tailor_resume] rate limit — returning 429 retry_after={retry_secs}s")
            raise HTTPException(
                status_code=429,
                detail=json.dumps({"rate_limited": True, "retry_after": retry_secs})
            )
        print(f"Unexpected error in tailor_resume: {e}")
        raise HTTPException(status_code=500, detail=str(e))



async def _generate_cover_letter(
    resume_text: str,
    hyperlinks: dict,
    job_text: str,
    stem: str,
    date_str: str,
    time_str: str,
    candidate_name: str,
    company_role: str,
) -> str | None:
    """
    Generate a professional cover letter PDF using Gemini and save it to OUTPUT_CL_DIR.
    Returns the filename on success, None on failure.
    """
    from reportlab.lib.pagesizes  import letter
    from reportlab.lib.styles     import ParagraphStyle
    from reportlab.lib.units      import inch
    from reportlab.lib            import colors
    from reportlab.platypus       import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums      import TA_LEFT, TA_JUSTIFY

    # Build the prompt
    today = datetime.now().strftime("%B %d, %Y")
    email_uri = hyperlinks.get("Email", "")
    email_addr = email_uri.replace("mailto:", "").strip() if email_uri else ""
    linkedin_url = hyperlinks.get("LinkedIn", "")

    prompt = f"""You are a professional cover letter writer. Write a tailored, polished cover letter based on the resume and job description below.

FORMAT RULES:
- Return ONLY a JSON object. No markdown, no code fences, no explanation.
- Every field must be plain text only — no markdown, no asterisks, no bold tags.

JSON schema:
{{
  "candidate_name": "full name from resume",
  "candidate_email": "{email_addr}",
  "candidate_phone": "phone number from resume",
  "candidate_linkedin": "{linkedin_url}",
  "company_name": "company name from job description",
  "hiring_manager": "hiring manager name if mentioned, otherwise empty string",
  "company_address": "company address if mentioned, otherwise empty string",
  "date": "{today}",
  "opening_paragraph": "1-3 sentences: who you are, what role you are applying for, and why you are excited about this specific company/role. Be specific, not generic.",
  "middle_paragraph": "2-4 sentences: 1-2 of your strongest and most relevant experiences or projects directly tied to the job requirements. Mention specific technologies, results, or achievements from the resume.",
  "skills_paragraph": "2-3 sentences: 2-3 key technical skills or projects aligned to the job. This paragraph is optional — only include if there is genuinely more to add beyond the middle paragraph. If not needed, return empty string.",
  "closing_paragraph": "2-3 sentences: express enthusiasm, summarise the value you bring, and include a polite call to action (e.g. would welcome the opportunity to discuss further).",
  "sign_off": "Sincerely"
}}

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_text}

JSON:"""

    # Call Gemini with retry
    gemini_data = None
    for attempt in range(4):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    GEMINI_URL,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096, "thinkingConfig": {"thinkingBudget": 0}},
                    },
                )
                resp.raise_for_status()
                gemini_data = resp.json()
                break
        except httpx.HTTPStatusError as e:
            print(f"[cover letter] Gemini HTTP error {e.response.status_code}: {e.response.text[:200]}")
            if e.response.status_code == 429:
                await asyncio.sleep(15 * (attempt + 1))
                continue
            break
        except Exception as ex:
            print(f"[cover letter] Gemini request exception: {ex}")
            break

    if not gemini_data:
        print("[cover letter] No gemini_data — returning None")
        return None

    try:
        candidates = gemini_data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", [])
        raw = "".join(p.get("text", "") for p in parts).strip()
        clean = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        start = clean.index("{")
        end   = clean.rindex("}") + 1
        cl = json.loads(clean[start:end])
    except Exception as ex:
        print(f"[cover letter] JSON parse error: {ex} | raw[:200]: {raw[:200] if raw else 'empty'}")
        return None

    # ── Build the cover letter PDF ────────────────────────────────────────
    # Sanitize candidate_name for filename
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '', candidate_name).strip()
    cl_filename = f"{sanitized_name}-{company_role}-CoverLetter-{date_str}_{time_str}.pdf"
    cl_path     = OUTPUT_CL_DIR / cl_filename

    MARGIN = 0.75 * inch
    doc = SimpleDocTemplate(
        str(cl_path), pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Cover Letter - {candidate_name}",
        author=cl.get("candidate_name", ""),
        subject="Tailored Cover Letter",
        creator="Resume Tailor",
        
    )

    normal   = ParagraphStyle("Normal",   fontName="Helvetica",      fontSize=10,   leading=14, spaceAfter=0)
    bold_p   = ParagraphStyle("Bold",     fontName="Helvetica-Bold", fontSize=10,   leading=14, spaceAfter=0)
    justify  = ParagraphStyle("Justify",  fontName="Helvetica",      fontSize=10,   leading=14, spaceAfter=10, alignment=TA_JUSTIFY)
    small    = ParagraphStyle("Small",    fontName="Helvetica",      fontSize=9,    leading=13, spaceAfter=0, textColor=colors.HexColor("#555555"))

    def esc(t): return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []

    # Header — candidate info
    story.append(Paragraph(esc(cl.get("candidate_name", "")), bold_p))

    # Line 1: email | phone | date
    line1 = [p for p in [
        esc(cl.get("candidate_email", "")),
        esc(cl.get("candidate_phone", "")),
        esc(cl.get("date", "")),
    ] if p]
    story.append(Paragraph(" | ".join(line1), small))

    # Line 2: linkedin (optional, own line)
    linkedin = esc(cl.get("candidate_linkedin", ""))
    if linkedin:
        story.append(Paragraph(linkedin, small))

    story.append(Spacer(1, 0.18 * inch))

    # Company block
    company_name = esc(cl.get("company_name", ""))
    hiring_mgr   = esc(cl.get("hiring_manager", ""))
    company_addr = esc(cl.get("company_address", ""))
    if company_name:
        story.append(Paragraph(company_name, normal))
    if hiring_mgr:
        story.append(Paragraph(hiring_mgr, normal))
    if company_addr:
        story.append(Paragraph(company_addr, normal))
    story.append(Spacer(1, 0.14 * inch))

    # Salutation
    salutation = f"Dear {hiring_mgr}," if hiring_mgr else "Dear Hiring Manager,"
    story.append(Paragraph(salutation, normal))
    story.append(Spacer(1, 0.1 * inch))

    # Body paragraphs
    for key in ["opening_paragraph", "middle_paragraph", "skills_paragraph", "closing_paragraph"]:
        text = cl.get(key, "").strip()
        if text:
            story.append(Paragraph(esc(text), justify))

    story.append(Spacer(1, 0.12 * inch))

    # Sign off
    sign_off = esc(cl.get("sign_off", "Sincerely"))
    story.append(Paragraph(sign_off + ",", normal))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(esc(cl.get("candidate_name", "")), normal))

    try:
        doc.build(story)
        return cl_filename
    except Exception:
        return None


def _build_resume_pdf(data: dict, output_path: str):
    """
    Build an ATS-optimized PDF resume.

    ATS requirements met:
    - Single-column linear layout (no tables, no frames, no columns)
    - Helvetica (Type1) fonts — always embedded, reliably parsed by ATS
    - Plain Unicode text — no ligatures, no special glyphs
    - Reading order matches visual order (top-to-bottom, left-to-right)
    - PDF metadata (Title, Author, Subject) for ATS document indexing
    - No images or graphics in the text flow
    - Section headings preserve the original resume casing
    - Bullet points as plain Unicode bullet character (U+2022), not image glyphs
    """
    from reportlab.lib.pagesizes  import letter
    from reportlab.lib.styles     import ParagraphStyle
    from reportlab.lib.units      import inch
    from reportlab.lib            import colors
    from reportlab.platypus       import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.enums      import TA_CENTER

    MARGIN = 0.6 * inch
    author = data.get("name", "Resume")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title=f"Resume - {author}",
        author=author,
        subject="Tailored Resume",
        creator="Resume Tailor",
    )

    # ── Styles ────────────────────────────────────────────────────────────────
    name_style = ParagraphStyle(
        "Name",
        fontName="Helvetica-Bold",
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=2,
        leading=20,
    )
    contact_style = ParagraphStyle(
        "Contact",
        fontName="Helvetica",
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=6,
        leading=12,
        textColor=colors.HexColor("#333333"),
    )
    section_title_style = ParagraphStyle(
        "SectionTitle",
        fontName="Helvetica-Bold",
        fontSize=10,
        spaceBefore=8,
        spaceAfter=1,
        textColor=colors.black,
        leading=11,
    )
    entry_heading_style = ParagraphStyle(
        "EntryHeading",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        spaceBefore=4,
        spaceAfter=0.5,
        leading=11,
    )
    entry_sub_style = ParagraphStyle(
        "EntrySub",
        fontName="Helvetica-Oblique",
        fontSize=9,
        spaceAfter=1.5,
        leading=10,
        textColor=colors.HexColor("#555555"),
    )
    summary_body_style = ParagraphStyle(
        "SummaryBody",
        fontName="Helvetica",
        fontSize=9.5,
        spaceBefore=4,
        spaceAfter=1.5,
        leading=11,   # tight single-spacing — matches original resume
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        fontName="Helvetica",
        fontSize=9.5,  # bumped from 9 for readability
        leftIndent=12,
        firstLineIndent=0,
        spaceAfter=1,
        leading=10.5,  # proportional to font bump
    )
    skills_style = ParagraphStyle(
        "Skills",
        fontName="Helvetica",
        fontSize=9.5,  # bumped from 9 for readability
        spaceAfter=1.5,
        leading=10.5,  # proportional to font bump
    )

    hyperlinks = data.get("hyperlinks", {})

    def linkify(text: str) -> str:
        for label, url in hyperlinks.items():
            if label and label in text:
                escaped = url.replace("&", "&amp;")
                text = text.replace(
                    label,
                    f'<link href="{escaped}"><u><font color="#0066CC">{label}</font></u></link>',
                    1,
                )
        return text

    def safe_xml(text: str) -> str:
        """Escape characters that break ReportLab's XML parser."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    name    = as_str(data.get("name"))
    contact = as_str(data.get("contact"))
    if name:
        story.append(Paragraph(safe_xml(name), name_style))
    if contact:
        story.append(Paragraph(linkify(safe_xml(contact)), contact_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=4))

    # ── Sections ──────────────────────────────────────────────────────────────
    for section in data.get("sections", []):
        title      = as_str(section.get("title"))
        title_upper = title.upper()
        is_skills  = "SKILL" in title_upper
        is_edu     = "EDUC" in title_upper
        is_proj    = "PROJ" in title_upper

        story.append(Paragraph(safe_xml(title), section_title_style))
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.HexColor("#aaaaaa"),
            spaceAfter=3,
        ))

        is_summary = "SUMMARY" in title_upper and "SKILL" not in title_upper

        for entry in section.get("entries", []):
            heading    = as_str(entry.get("heading"))
            subheading = as_str(entry.get("subheading"))
            bullets    = normalize_list_of_strings(entry.get("bullets"))
            _plain_skill_bullets: list[str] = []  # collected for 2-col flush after loop

            # ── Heading ───────────────────────────────────────────────────────
            if not is_skills and heading:
                if is_proj:
                    # Projects: combine heading and subheading on one line
                    if subheading:
                        combined = f"<b>{safe_xml(heading)}</b> | <i>{safe_xml(subheading)}</i>"
                        subheading = ""  # consumed
                    else:
                        combined = f"<b>{safe_xml(heading)}</b>"
                    proj_style = ParagraphStyle(
                        "ProjHeading",
                        fontName="Helvetica",
                        fontSize=9.5,
                        spaceBefore=6,
                        spaceAfter=2,
                        leading=12,
                    )
                    story.append(Paragraph(combined, proj_style))
                elif is_summary:
                    pass  # summary text is in bullets, not heading — skip heading render
                else:
                    story.append(Paragraph(safe_xml(heading), entry_heading_style))

            # ── Subheading ────────────────────────────────────────────────────
            if subheading and not is_skills and not is_summary:
                story.append(Paragraph(safe_xml(subheading), entry_sub_style))

            # ── Bullets ───────────────────────────────────────────────────────
            for b in bullets:
                b = b.strip()
                if not b:
                    continue

                if is_summary:
                    # Summary: render as plain prose paragraph, no bullet
                    # Strip leading bullet character if AI included one
                    b_clean = re.sub(r"^[•\-\*]\s*", "", b).strip()
                    if b_clean:
                        story.append(Paragraph(safe_xml(b_clean), summary_body_style))

                elif is_skills:
                    _non_skill_prefixes = {
                        "email", "phone", "tel", "address", "linkedin", "github",
                        "portfolio", "website", "url", "name", "gpa", "university",
                        "college", "school", "location", "city",
                    }
                    m = re.match(r"^([A-Za-z0-9 &/+-]+:)\s*(.*)$", b)
                    if m and m.group(1).rstrip(":").strip().lower() not in _non_skill_prefixes:
                        label_part = safe_xml(m.group(1))
                        value_part = safe_xml(m.group(2))
                        story.append(Paragraph(
                            f"<b>{label_part}</b> {value_part}",
                            skills_style,
                        ))
                    elif not m:
                        # Plain bullet — collected below for 2-col table (SKILLS SUMMARY)
                        _plain_skill_bullets.append(b)
                        continue
                    # else: matched but was a contact/header line — silently skip it

                elif is_edu:
                    story.append(Paragraph(safe_xml(b), entry_sub_style))

                else:
                    story.append(Paragraph(
                        safe_xml(b),
                        bullet_style,
                        bulletText="•",
                    ))

            # ── Flush plain skill bullets as 2-column table (SKILLS SUMMARY) ──────
            if _plain_skill_bullets:
                from reportlab.platypus import Table, TableStyle
                from reportlab.lib import colors as rl_colors
                col_bullet_style = ParagraphStyle(
                    "ColBullet",
                    fontName="Helvetica",
                    fontSize=9.5,
                    leading=12,
                    leftIndent=8,
                )
                usable_width = doc.width
                col_w = usable_width / 2
                # Estimate max chars that fit in a single column at current font size
                # Helvetica ~0.55 width ratio at fontSize 9.5
                _max_col_chars = int(col_w / (col_bullet_style.fontSize * 0.55))

                # Separate items that are too long for a half-width column
                short_items = [b for b in _plain_skill_bullets if len(b) <= _max_col_chars]
                long_items  = [b for b in _plain_skill_bullets if len(b) >  _max_col_chars]

                # Build table: long items span full width, short items pair in 2 cols
                # Interleave short items: longest with shortest to balance row heights
                sorted_short = sorted(short_items, key=len, reverse=True)
                mid = (len(sorted_short) + 1) // 2
                left_col  = sorted_short[:mid]
                right_col = sorted_short[mid:][::-1]
                while len(right_col) < len(left_col):
                    right_col.append("")

                table_data = []
                span_rows: list[int] = []

                # Add long items as full-width spanned rows first
                for item in long_items:
                    span_rows.append(len(table_data))
                    full_para = Paragraph(f"• {safe_xml(item)}", col_bullet_style)
                    table_data.append([full_para, Paragraph("", col_bullet_style)])

                # Add paired short items
                for l, r in zip(left_col, right_col):
                    l_para = Paragraph(f"• {safe_xml(l)}", col_bullet_style) if l else Paragraph("", col_bullet_style)
                    r_para = Paragraph(f"• {safe_xml(r)}", col_bullet_style) if r else Paragraph("", col_bullet_style)
                    table_data.append([l_para, r_para])

                tbl = Table(table_data, colWidths=[col_w, col_w])
                style_cmds = [
                    ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
                    ("TOPPADDING",    (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
                # Span full-width rows across both columns
                for row_idx in span_rows:
                    style_cmds.append(("SPAN", (0, row_idx), (1, row_idx)))
                tbl.setStyle(TableStyle(style_cmds))
                story.append(tbl)

        story.append(Spacer(1, 2))

    doc.build(story)


@app.get("/api/download/{filename}")
async def download_resume(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/download-cl/{filename}")
async def download_cover_letter(filename: str):
    file_path = OUTPUT_CL_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Cover letter file not found.")
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/history")
def list_history():
    files = []
    for f in sorted(OUTPUT_DIR.glob("*.pdf"), key=os.path.getmtime, reverse=True):
        files.append({
            "filename":   f.name,
            "size_kb":    round(f.stat().st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"history": files, "ttl_days": OUTPUT_TTL_DAYS}


@app.delete("/api/history/{filename}")
def delete_history_file(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    file_path.unlink()
    return {"success": True, "deleted": filename}


@app.delete("/api/history")
def clear_history():
    deleted = []
    for f in OUTPUT_DIR.glob("*.pdf"):
        f.unlink()
        deleted.append(f.name)
    return {"success": True, "deleted": deleted}


@app.get("/api/history-cl")
def list_cl_history():
    files = []
    for f in sorted(OUTPUT_CL_DIR.glob("*.pdf"), key=os.path.getmtime, reverse=True):
        files.append({
            "filename":   f.name,
            "size_kb":    round(f.stat().st_size / 1024, 1),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"history": files, "ttl_days": OUTPUT_TTL_DAYS}


@app.delete("/api/history-cl/{filename}")
def delete_cl_history_file(filename: str):
    file_path = OUTPUT_CL_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    file_path.unlink()
    return {"success": True, "deleted": filename}


@app.delete("/api/history-cl")
def clear_cl_history():
    deleted = []
    for f in OUTPUT_CL_DIR.glob("*.pdf"):
        f.unlink()
        deleted.append(f.name)
    return {"success": True, "deleted": deleted}


@app.get("/api/preview-resume/{filename}")
async def preview_resume(filename: str):
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    safe_name = Path(file.filename).name
    save_path = UPLOAD_DIR / safe_name
    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "success":       True,
        "filename":      safe_name,
        "original_name": file.filename,
        "saved_at":      str(save_path),
        "uploaded_at":   datetime.now().isoformat(),
    }


@app.get("/api/resumes")
def list_resumes():
    files = []
    for f in sorted(UPLOAD_DIR.glob("*.pdf"), key=os.path.getmtime, reverse=True):
        files.append({
            "filename":    f.name,
            "size_kb":     round(f.stat().st_size / 1024, 1),
            "uploaded_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"resumes": files}


@app.delete("/api/resumes/{filename}")
def delete_resume(filename: str):
    file_path = UPLOAD_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    file_path.unlink()
    return {"success": True, "deleted": filename}

# ── Static file serving (production) ──────────────────────────────────────────
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(str(FRONTEND_DIST / "index.html"))