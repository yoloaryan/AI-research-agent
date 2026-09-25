"""
api.py — AI Research Studio FastAPI backend
============================================
Endpoints:
  POST /research                          — run pipeline, store report
  GET  /reports/{report_id}               — fetch a stored report
  GET  /reports                           — list all stored reports
  GET  /reports/{report_id}/download/markdown
  GET  /reports/{report_id}/download/pdf
  GET  /health
"""
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from pipeline import run_research_pipeline

# ── PDF generation ────────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

logger = logging.getLogger("api")

# ── Storage path ──────────────────────────────────────────────────────────────
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Research Studio API",
    version="2.0.0",
    description="Deep research API powered by a multi-agent pipeline.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(data):
    return {"success": True, "data": data, "error": None}


def _err(message: str, status: int = 500):
    raise HTTPException(status_code=status, detail={"success": False, "data": None, "error": message})


def _safe_report_id(report_id: str) -> str:
    """Validate and sanitize report_id to prevent path traversal."""
    clean = re.sub(r"[^a-f0-9\-]", "", report_id.lower())
    if len(clean) != 36 or clean.count("-") != 4:
        raise HTTPException(status_code=400, detail={"success": False, "data": None, "error": "Invalid report ID."})
    return clean


def _save_report(result: dict) -> None:
    """Persist report JSON and Markdown to disk."""
    rid = result["report_id"]
    # JSON
    json_path = REPORTS_DIR / f"{rid}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # Markdown
    md_path = REPORTS_DIR / f"{rid}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(result.get("report", ""))


def _load_report(report_id: str) -> dict:
    rid = _safe_report_id(report_id)
    json_path = REPORTS_DIR / f"{rid}.json"
    if not json_path.exists():
        _err("Report not found.", 404)
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def _build_pdf(result: dict) -> bytes:
    """Generate a professional PDF from a report dict. Returns bytes."""
    from io import BytesIO
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=result.get("topic", "Research Report"),
        author="AI Research Studio",
    )

    styles = getSampleStyleSheet()

    # ── Custom styles ─────────────────────────────────────────────────────────
    brand_style = ParagraphStyle(
        "Brand",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#6767d9"),
        fontName="Helvetica-Bold",
        spaceAfter=0,
        alignment=TA_LEFT,
    )
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#0f0f0f"),
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#888888"),
        spaceAfter=16,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#111827"),
        fontName="Helvetica-Bold",
        spaceBefore=18,
        spaceAfter=6,
        borderPad=0,
    )
    h3_style = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#374151"),
        fontName="Helvetica-Bold",
        spaceBefore=12,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=16,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=8,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=14,
        bulletIndent=0,
        spaceAfter=4,
    )
    source_style = ParagraphStyle(
        "Source",
        parent=body_style,
        fontSize=9,
        textColor=colors.HexColor("#555555"),
        leftIndent=10,
        spaceAfter=4,
    )

    story = []

    # ── Brand header ──────────────────────────────────────────────────────────
    story.append(Paragraph("✦ AI RESEARCH STUDIO", brand_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e6e8"), spaceAfter=10))

    # ── Title ─────────────────────────────────────────────────────────────────
    topic = result.get("topic", "Research Report")
    story.append(Paragraph(topic, title_style))

    created_at = result.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        date_str = dt.strftime("%B %d, %Y at %H:%M UTC")
    except Exception:
        date_str = created_at
    story.append(Paragraph(f"Generated: {date_str}  •  Report ID: {result.get('report_id', '')}", meta_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e6e8"), spaceAfter=16))

    # ── Parse Markdown-ish report into PDF flowables ──────────────────────────
    report_md = result.get("report", "No report generated.")
    lines = report_md.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 4))
            continue
        if stripped.startswith("# "):
            # Already using topic as title; skip duplicate H1
            continue
        elif stripped.startswith("## "):
            story.append(Paragraph(stripped[3:], h2_style))
        elif stripped.startswith("### "):
            story.append(Paragraph(stripped[4:], h3_style))
        elif stripped.startswith("- **") or stripped.startswith("* **") or stripped.startswith("- "):
            # Bullet: strip leading marker
            text = re.sub(r"^[-*]\s+", "", stripped)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            story.append(Paragraph(f"• {text}", bullet_style))
        elif re.match(r"^\d+\.\s+", stripped):
            text = re.sub(r"^\d+\.\s+", "", stripped)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            story.append(Paragraph(f"• {text}", bullet_style))
        else:
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", stripped)
            text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
            story.append(Paragraph(text, body_style))

    # ── Sources cards ─────────────────────────────────────────────────────────
    sources = result.get("sources", [])
    if sources:
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e6e8"), spaceAfter=6))
        story.append(Paragraph("Sources", h2_style))
        for s in sources[:10]:
            url = s.get("url", "")
            title = s.get("title") or s.get("domain", url)
            link = f'<link href="{url}" color="#5b5bd6">{title}</link>' if url else title
            story.append(Paragraph(f"• {link}  <font color=\"#888888\" size=\"8\">{url}</font>", source_style))

    # ── Page numbers via canvas callback ─────────────────────────────────────
    def _add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#aaaaaa"))
        canvas.drawRightString(
            A4[0] - 2.5 * cm,
            1.5 * cm,
            f"Page {doc.page}",
        )
        canvas.drawString(2.5 * cm, 1.5 * cm, "AI Research Studio — Confidential")
        canvas.restoreState()

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    return buf.getvalue()


# ── Request models ────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500,
                       description="The research topic or question.")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0", "pdf_available": PDF_AVAILABLE}


@app.post("/research")
async def research(request: ResearchRequest):
    topic = request.topic.strip()
    if not topic:
        _err("Research topic cannot be empty.", 400)

    try:
        result = await asyncio.to_thread(run_research_pipeline, topic)
    except Exception as exc:
        logger.exception("Unhandled pipeline error")
        _err(f"Research pipeline failed unexpectedly: {type(exc).__name__}. Please try again.", 500)

    if result.get("status") == "failed":
        # Pipeline returned a partial failure — send it through with 422
        raise HTTPException(
            status_code=422,
            detail={"success": False, "data": result, "error": result.get("error", "Pipeline failed.")},
        )

    _save_report(result)
    return _ok(result)


@app.get("/reports")
def list_reports():
    """Return a list of all stored reports (metadata only)."""
    reports = []
    for json_file in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            reports.append({
                "report_id": data.get("report_id"),
                "topic": data.get("topic"),
                "status": data.get("status"),
                "created_at": data.get("created_at"),
            })
        except Exception:
            continue
    return _ok(reports)


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    result = _load_report(report_id)
    return _ok(result)


@app.get("/reports/{report_id}/download/markdown")
def download_markdown(report_id: str):
    rid = _safe_report_id(report_id)
    md_path = REPORTS_DIR / f"{rid}.md"
    if not md_path.exists():
        # Regenerate from JSON if MD file is missing
        result = _load_report(rid)
        md_path.write_text(result.get("report", ""), encoding="utf-8")
    return FileResponse(
        path=str(md_path),
        media_type="text/markdown",
        filename=f"research-report-{rid[:8]}.md",
        headers={"Content-Disposition": f'attachment; filename="research-report-{rid[:8]}.md"'},
    )


@app.get("/reports/{report_id}/download/pdf")
def download_pdf(report_id: str):
    if not PDF_AVAILABLE:
        _err("PDF generation is not available. Install reportlab: pip install reportlab", 503)

    rid = _safe_report_id(report_id)
    pdf_path = REPORTS_DIR / f"{rid}.pdf"

    if not pdf_path.exists():
        # Generate and cache PDF
        result = _load_report(rid)
        pdf_bytes = _build_pdf(result)
        pdf_path.write_bytes(pdf_bytes)

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"research-report-{rid[:8]}.pdf",
        headers={"Content-Disposition": f'attachment; filename="research-report-{rid[:8]}.pdf"'},
    )


# ── Legacy compat ─────────────────────────────────────────────────────────────
@app.post("/api/research")
async def research_legacy(request: ResearchRequest):
    """Backwards-compatible alias for /research."""
    return await research(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        timeout_keep_alive=300,
    )
