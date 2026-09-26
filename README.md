# AI Research Studio

A premium, local AI research workspace powered by a multi-agent pipeline.
Search the web → inspect primary sources → synthesize a structured report → critique the result — in one seamless workflow.

![Pipeline](https://img.shields.io/badge/pipeline-Search%20%E2%86%92%20Reader%20%E2%86%92%20Writer%20%E2%86%92%20Critic-6767d9)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-2.0-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

- **Multi-agent pipeline** — Search Agent → Reader Agent → Writer → Critic
- **Structured Markdown reports** — 8-section format (Executive Summary, Key Findings, Analysis, Evidence, Limitations, Conclusion, Sources)
- **Persistent reports** — each report gets a unique `report_id`, saved to disk as JSON + Markdown + PDF
- **Share URLs** — `http://localhost:5500/?report=<id>` — shareable, bookmarkable, survives refresh
- **PDF download** — professional ReportLab-generated PDF with branding and page numbers
- **Markdown download** — clean `.md` export
- **Critic review** — structured 6-section quality review
- **Source cards** — extracted URLs displayed as clickable cards
- **Research trace panel** — see exactly what Search and Reader returned
- **History** — sidebar shows previous sessions, re-loadable from backend
- **Dark / light theme**
- **Zero CDN dependency** — all JS libs bundled locally

---

## Project Structure

```
AI-research/
├── agents.py           # LLM agents + writer/critic chains
├── pipeline.py         # Search → Reader → Writer → Critic pipeline
├── tools.py            # Tavily search + URL scraper tools
├── api.py              # FastAPI backend (research, reports, PDF/MD download)
├── .env.example        # API key template (copy to .env)
├── requirement.txt     # Core dependencies
├── requirements-web.txt# FastAPI / uvicorn
├── reports/            # Auto-created — persisted report files (gitignored)
└── frontend/
    ├── index.html
    ├── app.js
    ├── style.css
    ├── lucide.min.js   # Icons (bundled locally)
    ├── marked.min.js   # Markdown parser (bundled locally)
    └── purify.min.js   # DOMPurify HTML sanitizer (bundled locally)
```

---

## Setup

### 1. Clone & create virtual environment

```bash
git clone https://github.com/your-username/AI-research.git
cd AI-research
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirement.txt
pip install -r requirements-web.txt
pip install reportlab          # PDF generation
```

Or with `uv`:

```bash
uv pip install -r requirement.txt -r requirements-web.txt reportlab
```

### 3. Set up API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Key | Get it from |
|-----|-------------|
| `TAVILY_API_KEY` | https://app.tavily.com |
| `GROQ_API_KEY` | https://console.groq.com |
| `GROQ_MODEL` | See https://console.groq.com/docs/models (default: `openai/gpt-oss-120b`) |

---

## Running

**Terminal 1 — Backend:**

```bash
.venv/bin/uvicorn api:app --reload --port 8000
```

**Terminal 2 — Frontend:**

```bash
python3 -m http.server 5500 --directory frontend/
```

Open **http://localhost:5500**

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/research` | Run pipeline, get + persist report |
| `GET` | `/reports` | List all stored reports |
| `GET` | `/reports/{id}` | Fetch a specific report |
| `GET` | `/reports/{id}/download/markdown` | Download `.md` |
| `GET` | `/reports/{id}/download/pdf` | Download PDF |
| `GET` | `/health` | Health check |

All responses use: `{"success": bool, "data": {...}, "error": null}`

Interactive docs: **http://localhost:8000/docs**

---

## Share a Report

After research completes:
1. Click the **Share** button in the toolbar
2. The URL `http://localhost:5500/?report=<id>` is copied to clipboard
3. Anyone on the same machine can open that URL to view the exact same report
4. The report survives page refresh (loaded from `reports/<id>.json`)

---

## Tech Stack

| Layer | Tech |
|-------|------|
| LLM | Groq API (`openai/gpt-oss-120b`) |
| Search | Tavily API |
| Scraping | BeautifulSoup + requests |
| Agent framework | LangChain + LangGraph |
| Backend | FastAPI + uvicorn |
| PDF | ReportLab |
| Frontend | Vanilla HTML / CSS / JS |
| Icons | Lucide (local) |
| Markdown | marked.js + DOMPurify (local) |

---

## Deploy to Render

You can deploy this application directly to [Render](https://render.com) as a Web Service.

### Option 1: Automatic Blueprint (Recommended)
1. Go to [Render Dashboard](https://dashboard.render.com/) -> **New** -> **Blueprint**.
2. Select your repository `AI-research-agent`.
3. Render will auto-detect [`render.yaml`](file:///Users/aryangupta/Desktop/AI-research/render.yaml).
4. Enter your environment variables (`GROQ_API_KEY`, `TAVILY_API_KEY`).
5. Click **Apply**.

### Option 2: Manual Web Service
1. In Render, click **New +** -> **Web Service**.
2. Connect your repository.
3. Configure the settings:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api:app --host 0.0.0.0 --port $PORT`
4. Under **Environment Variables**, add:
   - `GROQ_API_KEY`: Your Groq API key
   - `TAVILY_API_KEY`: Your Tavily API key
   - `GROQ_MODEL`: `qwen/qwen3.8-27b`
5. Click **Deploy Web Service**.

---

## License

MIT

