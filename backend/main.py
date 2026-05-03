from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_purge_loop())
    yield

app = FastAPI(title="Resume Tailor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

_quota = {
    "date":  datetime.now().date(),
    "used":  0,
}

def _quota_reset_if_new_day():
    today = datetime.now().date()
    if _quota["date"] != today:
        _quota["date"] = today
        _quota["used"] = 0

def quota_increment():
    _quota_reset_if_new_day()
    _quota["used"] += 1

def quota_snapshot() -> dict:
    _quota_reset_if_new_day()
    used      = _quota["used"]
    remaining = max(0, GEMINI_DAILY_LIMIT - used)
    # seconds until midnight
    now       = datetime.now()
    midnight  = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    secs_left = int((midnight - now).total_seconds())
    return {
        "used":        used,
        "remaining":   remaining,
        "limit":       GEMINI_DAILY_LIMIT,
        "resets_in_s": secs_left,
        "resets_at":   midnight.isoformat(),
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
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "noscript", "iframe", "form"]):
        tag.decompose()

    candidate_selectors = [
        "[class*='job-description']", "[class*='jobDescription']",
        "[class*='job-content']",     "[class*='jobContent']",
        "[class*='description']",     "[id*='job-description']",
        "[id*='jobDescription']",     "article", "main",
    ]
    body_text = ""
    for sel in candidate_selectors:
        el = soup.select_one(sel)
        if el:
            body_text = el.get_text(separator=" ", strip=True)
            if len(body_text) > 300:
                break

    if not body_text:
        body_text = soup.get_text(separator=" ", strip=True)

    body_text = re.sub(r"\s{2,}", " ", body_text).strip()
    return body_text[:4000]


@app.get("/")
def root():
    return {"message": "Resume Tailor API is running"}


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
            lines = [line.rstrip() for line in text.splitlines()]
            title_norm = section_title.strip().upper()
            captured: list[str] = []
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
                    # Stop if we hit a new all-caps section header (4+ chars, no lowercase)
                    if len(stripped) >= 4 and stripped == stripped.upper() and re.match(r"^[A-Z][A-Z0-9 &/\-]+$", stripped):
                        break
                    # Strip leading bullet characters before storing
                    clean = re.sub(r"^[\u2022\u2023\u25E6\-\*]\s*", "", stripped).strip()
                    clean = re.sub(r"^•\s*", "", clean).strip()
                    if clean:
                        captured.append(clean)
                elif stripped.upper() == title_norm:
                    collecting = True
            return [line for line in captured if line.strip()]

        original_skills_summary_bullets = extract_plain_section_bullets("SKILLS SUMMARY", resume_text)

        import asyncio

        async def call_gemini(prompt: str, temperature: float = 0.1, max_tokens: int = 1024) -> str:
            """Call Gemini API with retry logic. Returns response text."""
            for attempt in range(4):
                attempt_start = perf_counter()
                print(f"[call_gemini] attempt={attempt+1}/4 temperature={temperature} max_tokens={max_tokens} starting")
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
                    retry_after = e.response.headers.get("retry-after")
                    print(f"[call_gemini] attempt={attempt+1} http error elapsed={elapsed:.1f}s status={e.response.status_code} retry_after={retry_after}")
                    if e.response.status_code == 403:
                        raise Exception("Invalid GEMINI_API_KEY.")
                    if e.response.status_code == 429:
                        wait_time = int(retry_after) if retry_after else 15 * (attempt + 1)
                        print(f"[call_gemini] rate limited — waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    raise Exception(f"Gemini API error {e.response.status_code}")
                except Exception as e:
                    elapsed = perf_counter() - attempt_start
                    print(f"[call_gemini] attempt={attempt+1} failed elapsed={elapsed:.1f}s error={e}")
                    if "Could not reach" in str(e) or "Invalid GEMINI" in str(e):
                        raise
                    if attempt == 3:
                        raise Exception(f"AI call failed: {str(e)}")
                    await asyncio.sleep(2 ** attempt)  # brief backoff for other transient errors
            raise Exception("Rate limit persisted after 4 attempts.")

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
  - tier1_hard_skills: specific named hard skills EXPLICITLY mentioned in the job description. Extract ONLY what appears in the text — do NOT infer, assume, or add skills not present. For retail/service roles extract things like POS systems, inventory software, or named tools mentioned. For tech roles extract languages, frameworks, platforms. For business roles extract named software or certifications. Maximum 12 items.
  - tier2_professional_concepts: concise workplace skill phrases (2-5 words) that match the domain of this specific role. For retail: customer engagement, inventory control, order fulfillment. For tech: system design, code review, CI/CD pipelines. Extract only what the job description actually emphasizes. Maximum 8 items.
  - exclude_from_bullets: skills or tools that would be factually inaccurate for this candidate based on the resume.
CRITICAL: Base ALL extraction purely on what the job description explicitly says. The role domain determines what keywords are relevant — a retail job should return retail keywords, a tech job should return tech keywords. Never mix domains.
Use these keywords when rewriting bullets in Part B.

PART B — RESUME REWRITE:
Rewrite the resume below to pass ATS screening for the given job description using the keywords you identified.

RULES — follow every one exactly:

RULE 1 — PRESERVE ALL CONTENT:
Keep every section, every entry, and every bullet. Never drop, merge, omit, or reorder anything.

RULE 2 — PRESERVE ALL NUMBERS EXACTLY:
Copy all numbers, percentages, dataset sizes, and counts character-for-character.
e.g. "530k+ entry dataset", "~75%", "30 epochs", "100+ students" must appear unchanged.

RULE 3 — KEYWORD INJECTION — HOW TO DO IT RIGHT:
Your goal is to weave keywords into bullets by replacing vague words with more specific ones from the keyword list, or by restructuring the sentence so the keyword is part of the core action — not tacked on at the end.

TIERED INJECTION RULES:
- Tier 1 keywords (hard technical skills): Only inject these if they already appear somewhere in the original resume. If a Tier 1 keyword does not appear in the original resume, do not inject it anywhere.
- Tier 2 keywords (professional concepts): Always consider these for injection wherever they fit naturally, regardless of whether they appear in the original resume.

CONCRETE EXAMPLES using this candidate's actual bullets:

  ORIGINAL:  "Implemented a RAG pipeline with TF-IDF chunk retrieval, reducing context window usage"
  REWRITTEN: "Implemented an NLP retrieval pipeline using RAG with TF-IDF chunk scoring, reducing context window usage and improving response relevance"
  WHY VALID: "NLP retrieval pipeline" replaces "RAG pipeline" — the keyword enriches the description of what was built.

  ORIGINAL:  "Evaluated multiple CNN and Graph-CNN models for pixel classification, documented results, and recommended the best model based on accuracy and runtime performance."
  REWRITTEN: "Evaluated CNN and Graph-CNN architectures for pixel classification, benchmarking accuracy and runtime to recommend the highest-performing model for research publication."
  WHY VALID: "research publication" replaced "best model" — it's a genuine enrichment of what "recommended" led to.

  ORIGINAL:  "Built cross-document synthesis engine with web search integration (DuckDuckGo), APA citation generation, and structured research report generation via LLM."
  REWRITTEN: "Built a cross-document NLP synthesis engine with web search integration (DuckDuckGo), APA citation generation, and structured research report generation via LLM."
  WHY VALID: "NLP synthesis engine" replaces "synthesis engine" — one word swap, no appending.

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
  - If the original resume has a SUMMARY section, rewrite it to naturally incorporate 2-3 relevant Tier 2 professional concepts from the job description, while preserving the candidate's actual background, tone, and length.
  - Do not shorten it. Do not bullet-point it. Keep it as a single prose paragraph matching the original length.
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

        for line in resume_text.splitlines():
            m = re.match(r"^([A-Za-z0-9 &/+-]+):\s*(.+)$", line.strip())
            if m:
                cat_key = m.group(1).strip().lower()
                if cat_key not in original_skill_lines:
                    original_skill_lines[cat_key] = m.group(2).strip()
                    original_skill_order.append(m.group(1).strip())

        def split_skill_items(skill_line: str) -> list[str]:
            return [item.strip() for item in skill_line.split(",") if item.strip()]

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
            for cat_display in original_skill_order:
                cat_key = cat_display.lower()
                # Languages: only simple single-token identifiers (Python, Java, SQL, C++)
                if cat_key == "languages":
                    if re.match(r"^[a-z][a-z0-9+#/]*$", skill_lower):
                        return cat_display
                    continue  # don't fall through to other categories
                if any(k in cat_key for k in ["framework", "library", "libraries"]):
                    # Only proper named libraries/frameworks
                    known_fw = {
                        "hadoop", "spark", "mlflow", "flask", "react", "next.js",
                        "node.js", "vue", "angular", "fastapi", "django",
                    }
                    if skill_lower in known_fw or re.match(r"^[a-z][a-z0-9.]+$", skill_lower):
                        return cat_display
                    continue
                if any(k in cat_key for k in ["data", "ai", "ml", "analytics", "machine learning"]):
                    return cat_display
                if any(k in cat_key for k in ["tool", "devops", "database", "db", "platform", "service"]):
                    return cat_display
            # No fallback — if nothing fits cleanly, don't inject
            return None

        skill_keywords = [kw.lower() for kw in tier1_keywords if kw.strip()]
        skill_items_per_cat: dict[str, list[str]] = {
            cat_display: split_skill_items(original_skill_lines[cat_display.lower()])
            for cat_display in original_skill_order
        }

        for cat_display, items in skill_items_per_cat.items():
            skill_items_per_cat[cat_display] = reorder_existing_items(items, skill_keywords)

        resume_lower = resume_text.lower()
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
            # Only inject tier1 skills if they appear in the original resume
            if re.search(rf"(?<!\w){re.escape(skill_lower)}(?!\w)", resume_lower):
                target_cat = choose_skill_category(skill)
                if target_cat and skill not in skill_items_per_cat.get(target_cat, []):
                    skill_items_per_cat[target_cat].append(skill)

        final_skill_lines: list[str] = [
            f"{cat_display}: {', '.join(skill_items_per_cat[cat_display])}"
            for cat_display in original_skill_order
        ]

        for section in resume_data.get("sections", []):
            title_upper = section.get("title", "").upper()
            if "SKILL" in title_upper:
                if "SKILLS SUMMARY" in title_upper or "SKILL SUMMARY" in title_upper:
                    # Always restore from original — AI mangles plain-bullet skill sections
                    if original_skills_summary_bullets:
                        section["entries"] = [{"heading": "", "subheading": "", "bullets": original_skills_summary_bullets}]
                    else:
                        # Fallback: use whatever AI returned if we have nothing original
                        current_bullets = [b for entry in section.get("entries", []) for b in normalize_list_of_strings(entry.get("bullets"))]
                        if not current_bullets:
                            section["entries"] = [{"heading": "", "subheading": "", "bullets": []}]
                    continue
                # Regular categorized skills section
                section["entries"] = [{"heading": "", "subheading": "", "bullets": final_skill_lines}]
                break

        # Post-process 3: Drop empty bullets
        for section in resume_data.get("sections", []):
            for entry in section.get("entries", []):
                entry["bullets"] = normalize_list_of_strings(entry.get("bullets"))

        # Post-process 4: Dynamic Tier 2 keyword injection
        # Strategy: for each tier2 keyword, find the bullet where it fits best
        # by looking for semantically related words already in the bullet.
        # Works for any domain — tech, retail, business, etc.

        used_tier2 = set()

        def _semantic_match_score(kw: str, bullet: str) -> float:
            """Score how well a tier2 keyword fits a bullet based on shared words."""
            kw_words = set(re.findall(r"[a-z]+", kw.lower())) - {
                "and", "or", "the", "a", "an", "in", "of", "to", "for", "with", "on", "at"
            }
            bullet_words = set(re.findall(r"[a-z]+", bullet.lower()))
            if not kw_words:
                return 0.0
            overlap = kw_words & bullet_words
            return len(overlap) / len(kw_words)

        def _inject_tier2_into_bullet(bullet: str, kw: str) -> str:
            """
            Try to inject kw naturally into bullet by replacing a vague ending phrase.
            If no good injection point found, return bullet unchanged.
            """
            # Patterns: replace weak ending phrases like "the best approach", "good results"
            # with the tier2 keyword phrase
            weak_endings = [
                r"(,?\s+(?:achieving|ensuring|enabling|providing|delivering|supporting|improving|maintaining)\s+[\w\s]{3,25})$",
                r"(,?\s+(?:effectively|efficiently|successfully|consistently)\s+[\w\s]{3,20})$",
                r"(,?\s+(?:good|strong|effective|positive|successful)\s+[\w\s]{3,20})$",
            ]
            for pattern in weak_endings:
                m = re.search(pattern, bullet, re.IGNORECASE)
                if m:
                    replacement = f", demonstrating {kw}"
                    candidate = bullet[:m.start()] + replacement
                    # Only use if shorter than original + 20 chars
                    if len(candidate) <= len(bullet) + 20:
                        return candidate
            return bullet  # no injection if no good fit

        for section in resume_data.get("sections", []):
            title_upper = section.get("title", "").upper()
            if "SKILL" in title_upper or "SUMMARY" in title_upper:
                continue
            for entry in section.get("entries", []):
                new_bullets = []
                for b in normalize_list_of_strings(entry.get("bullets")):
                    if len(used_tier2) < 4:  # cap at 4 injections per resume
                        for kw in tier2_keywords:
                            if kw in used_tier2:
                                continue
                            if kw.lower() in b.lower():
                                # Already present — count it
                                used_tier2.add(kw)
                                continue
                            score = _semantic_match_score(kw, b)
                            if score >= 0.4:  # at least 40% word overlap
                                b_new = _inject_tier2_into_bullet(b, kw)
                                if b_new != b:
                                    b = b_new
                                    used_tier2.add(kw)
                                    break
                    new_bullets.append(b)
                entry["bullets"] = new_bullets

        # extract_job_keywords removed — keywords come directly from main Gemini prompt (tier1_hard_skills / tier2_professional_concepts fields)

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

        all_keywords        = tier1_keywords + tier2_keywords
        original_resume_keywords = [kw for kw in all_keywords if keyword_present(kw, normalized_original_text)]
        matched_keywords = [kw for kw in all_keywords if keyword_present(kw, normalized_resume_text)]
        injected_keyword_list = [kw for kw in matched_keywords if kw not in original_resume_keywords]
        missing_keywords = [kw for kw in all_keywords if not keyword_present(kw, normalized_resume_text)]
        
        # For scoring: only count tier1 keywords that appear in original resume + all tier2 keywords
        tier1_in_original = [kw for kw in tier1_keywords if keyword_present(kw, normalized_original_text)]
        scoring_keywords = tier1_in_original + tier2_keywords  # Only these count toward coverage score
        matched_scoring_keywords = [kw for kw in scoring_keywords if keyword_present(kw, normalized_resume_text)]
        
        keyword_match_count = len(matched_scoring_keywords)
        keyword_total_count = len(scoring_keywords)
        keyword_injection_count = len(injected_keyword_list)
        missing_keywords = list(dict.fromkeys(missing_keywords))
        original_resume_keywords = list(dict.fromkeys(original_resume_keywords))
        injected_keyword_list = list(dict.fromkeys(injected_keyword_list))

        # ── Final event (100%)

        # Return final result
        final_result = {
            "success":               True,
            "output_filename":       output_filename,
            "cover_letter_filename": cover_filename_out,
            "scoring": {
                "tier1_keywords":          tier1_keywords,
                "tier2_keywords":          tier2_keywords,
                "excluded_kws":            excluded_kws,
                "tier2_injections_fired":  len(used_tier2),
                "keyword_injection_count": keyword_injection_count,
                "job_text_length":         len(job_text),
                "injected_tier2":          list(used_tier2),
                "quantified_bullets":      quantified_bullets,
                "total_bullets":           total_bullets,
                "quantification_rate":     quantification_rate,
                "matched_keywords":        keyword_match_count,
                "total_keywords":          keyword_total_count,
                "matched_keyword_list":    matched_scoring_keywords,
                "original_resume_keywords": original_resume_keywords,
                "injected_keywords":       injected_keyword_list,
                "missing_keywords":        missing_keywords,
            }
        }

        return final_result



    except HTTPException:
        raise
    except Exception as e:
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
        leading=12,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        fontName="Helvetica",
        fontSize=9,
        leftIndent=12,
        firstLineIndent=0,
        spaceAfter=1,
        leading=10,
    )
    skills_style = ParagraphStyle(
        "Skills",
        fontName="Helvetica",
        fontSize=9,
        spaceAfter=1.5,
        leading=10,
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

        is_summary = "SUMMARY" in title_upper

        for entry in section.get("entries", []):
            heading    = as_str(entry.get("heading"))
            subheading = as_str(entry.get("subheading"))
            bullets    = normalize_list_of_strings(entry.get("bullets"))

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
                    m = re.match(r"^([A-Za-z0-9 &/+-]+:)\s*(.*)$", b)
                    if m:
                        label_part = safe_xml(m.group(1))
                        value_part = safe_xml(m.group(2))
                        story.append(Paragraph(
                            f"<b>{label_part}</b> {value_part}",
                            skills_style,
                        ))
                    else:
                        # Plain bullet skills (e.g. Skills Summary section)
                        story.append(Paragraph(safe_xml(b), skills_style))

                elif is_edu:
                    story.append(Paragraph(safe_xml(b), entry_sub_style))

                else:
                    story.append(Paragraph(
                        safe_xml(b),
                        bullet_style,
                        bulletText="•",
                    ))

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