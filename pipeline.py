"""
pipeline.py — Multi-agent research pipeline
============================================
Search → Reader → Writer → Critic

Groq free tier: ~6 000–14 400 TPM depending on model.
Limits and cooldowns are applied ONLY where needed.
"""
import time
import re
import logging
import uuid
from datetime import datetime, timezone

from agents import build_reader_agent, build_search_agent, writer_chain, critic_chain

logger = logging.getLogger("pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Token / char budgets ─────────────────────────────────────────────────────
MAX_SEARCH   = 2000   # chars of search output sent to reader prompt
MAX_SCRAPED  = 1500   # chars of scraped content sent to writer
MAX_RESEARCH = 3000   # chars of combined research sent to writer
MAX_REPORT   = 2000   # chars of report sent to the critic

# Only sleep between steps if we actually used the API successfully.
# Groq 429s are handled by the retry function; don't add blind waits.
STEP_COOLDOWN = 4     # seconds between successful LLM calls


# ── Retry helper ─────────────────────────────────────────────────────────────

def _retry(fn, *args, retries=3, base_wait=12, **kwargs):
    """
    Call fn(*args, **kwargs).
    On HTTP 429 or 'rate_limit_exceeded', wait with increasing backoff and retry.
    On other errors, raise immediately.
    After all retries exhausted, raise the last error.
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            msg = str(exc)
            is_rate_limit = "429" in msg or "rate_limit_exceeded" in msg.lower()
            if is_rate_limit and attempt < retries - 1:
                wait = base_wait * (attempt + 1)
                logger.warning(
                    "Rate limit hit — waiting %ds (attempt %d/%d)…",
                    wait, attempt + 1, retries
                )
                time.sleep(wait)
                last_exc = exc
                continue
            raise   # non-rate-limit error or final retry — propagate
    raise last_exc  # should not reach here


# ── Source extraction ─────────────────────────────────────────────────────────

def _extract_sources(text: str) -> list[dict]:
    """
    Pull any URLs from a block of text and return them as source dicts.
    """
    sources = []
    seen = set()
    url_pattern = re.compile(r"https?://[^\s\"'<>)]+")
    title_url_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")

    # First try to grab Markdown-style [Title](URL) pairs
    for match in title_url_pattern.finditer(text):
        title, url = match.group(1), match.group(2)
        url = url.rstrip(".,;)")
        if url not in seen:
            seen.add(url)
            domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
            sources.append({"title": title, "url": url, "domain": domain, "snippet": ""})

    # Then grab any bare URLs not already captured
    for match in url_pattern.finditer(text):
        url = match.group(0).rstrip(".,;)")
        if url not in seen:
            seen.add(url)
            domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
            sources.append({"title": domain, "url": url, "domain": domain, "snippet": ""})

    return sources


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_research_pipeline(topic: str) -> dict:
    """
    Run the full Search → Reader → Writer → Critic pipeline.

    Returns a structured dict — never exposes raw LangChain objects.
    Partial results are returned on stage failures so the frontend always
    receives something useful.
    """
    report_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    state: dict = {
        "topic": topic,
        "report_id": report_id,
        "created_at": created_at,
        "status": "running",
        "search_results": "",
        "scraped_content": "",
        "report": "",
        "feedback": "",
        "sources": [],
        "stages": {
            "search": "pending",
            "reader": "pending",
            "writer": "pending",
            "critic": "pending",
        },
        "error": None,
    }

    # ── Step 1 – Search ───────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("SEARCH: Finding information on '%s'", topic)
    logger.info("=" * 55)
    state["stages"]["search"] = "running"

    try:
        search_agent = build_search_agent()
        search_result = _retry(
            search_agent.invoke,
            {"messages": [("user", f"Find 3-5 recent, reliable facts and sources about: {topic}")]}
        )
        raw_search = search_result["messages"][-1].content
        state["search_results"] = raw_search[:MAX_SEARCH]
        state["stages"]["search"] = "complete"
        logger.info("SEARCH complete — %d chars", len(state["search_results"]))
        time.sleep(STEP_COOLDOWN)
    except Exception as exc:
        state["stages"]["search"] = "failed"
        state["error"] = f"Search failed: {type(exc).__name__}: {exc}"
        state["status"] = "failed"
        logger.error("SEARCH failed: %s", exc)
        return state

    # ── Step 2 – Reader ───────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("READER: Scraping top source")
    logger.info("=" * 55)
    state["stages"]["reader"] = "running"

    try:
        reader_agent = build_reader_agent()
        reader_result = _retry(
            reader_agent.invoke,
            {
                "messages": [(
                    "user",
                    f"Pick one URL from the results below about '{topic}' and scrape it.\n\n"
                    f"{state['search_results'][:500]}"
                )]
            }
        )
        raw_scraped = reader_result["messages"][-1].content
        state["scraped_content"] = raw_scraped[:MAX_SCRAPED]
        state["stages"]["reader"] = "complete"
        logger.info("READER complete — %d chars", len(state["scraped_content"]))
        time.sleep(STEP_COOLDOWN)
    except Exception as exc:
        # Reader failure is non-fatal — proceed with search results only
        state["stages"]["reader"] = "failed"
        state["scraped_content"] = "(Reader stage failed — using search results only)"
        logger.warning("READER failed (continuing): %s", exc)

    # ── Step 3 – Writer ───────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("WRITER: Drafting research report")
    logger.info("=" * 55)
    state["stages"]["writer"] = "running"

    research_combined = (
        f"SEARCH RESULTS:\n{state['search_results']}\n\n"
        f"SCRAPED CONTENT:\n{state['scraped_content']}"
    )[:MAX_RESEARCH]

    try:
        report_text = _retry(
            writer_chain.invoke,
            {"topic": topic, "research": research_combined}
        )
        state["report"] = report_text
        state["sources"] = _extract_sources(state["search_results"] + "\n" + report_text)
        state["stages"]["writer"] = "complete"
        logger.info("WRITER complete — %d chars", len(report_text))
        time.sleep(STEP_COOLDOWN)
    except Exception as exc:
        state["stages"]["writer"] = "failed"
        state["status"] = "failed"
        state["error"] = f"Writer failed: {type(exc).__name__}: {exc}"
        logger.error("WRITER failed: %s", exc)
        return state

    # ── Step 4 – Critic ───────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("CRITIC: Reviewing report quality")
    logger.info("=" * 55)
    state["stages"]["critic"] = "running"

    try:
        feedback_text = _retry(
            critic_chain.invoke,
            {"report": state["report"][:MAX_REPORT]}
        )
        state["feedback"] = feedback_text
        state["stages"]["critic"] = "complete"
        logger.info("CRITIC complete — %d chars", len(feedback_text))
    except Exception as exc:
        # Critic failure is non-fatal — the report is still returned
        state["stages"]["critic"] = "failed"
        state["feedback"] = f"(Critic review unavailable: {type(exc).__name__})"
        logger.warning("CRITIC failed (report still returned): %s", exc)

    state["status"] = "completed"
    logger.info("Pipeline complete for topic: '%s' | report_id: %s", topic, report_id)
    return state


if __name__ == "__main__":
    topic = input("\nEnter a research topic: ").strip()
    result = run_research_pipeline(topic)
    print("\n--- REPORT ---")
    print(result.get("report", "No report generated."))
    print("\n--- FEEDBACK ---")
    print(result.get("feedback", "No feedback."))
