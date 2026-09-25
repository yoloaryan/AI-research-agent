from langchain.agents import create_agent          # works in langchain 1.4.x
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from tools import web_search, scrape_url
import os
from dotenv import load_dotenv

load_dotenv()

model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
llm = ChatGroq(model_name=model_name, temperature=0.2)


# ── Agents ───────────────────────────────────────────────────────────────────

def build_search_agent():
    return create_agent(model=llm, tools=[web_search])


def build_reader_agent():
    return create_agent(model=llm, tools=[scrape_url])


# ── Writer chain ─────────────────────────────────────────────────────────────
# Produces a structured Markdown research report.

writer_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert research writer. "
        "You produce clear, structured, evidence-based research reports in Markdown. "
        "Always cite only sources that actually appeared in the research input. "
        "Never invent URLs or source names. "
        "If a URL is not available, write 'URL unavailable'. "
        "Be thorough but concise."
    ),
    (
        "human",
        """Write a professional research report on the topic below.

TOPIC: {topic}

RESEARCH INPUT (search results + scraped content):
{research}

---

Output the report using EXACTLY this Markdown structure:

# [A descriptive title for this research topic]

## Executive Summary
A concise 3-4 sentence overview of the most important findings.

## Introduction
2-3 sentences explaining the topic, its relevance, and the scope of this research.

## Key Findings
- **Finding 1**: ...
- **Finding 2**: ...
- **Finding 3**: ...
- **Finding 4**: ...

## Detailed Analysis
Break the analysis into 2-3 logical subsections with ### headings.

### [Subsection 1 title]
...

### [Subsection 2 title]
...

## Evidence
Clearly present the factual evidence supporting your analysis. Distinguish facts from interpretation.

## Limitations
- List missing information, uncertainty, or possible bias in sources.
- Mention if sources are limited or the research window is narrow.

## Conclusion
2-3 sentences synthesising the key takeaway.

## Sources
List only sources that appeared in the research input above.
Format each as: - [Title or domain](URL) — brief description
If a URL is unavailable, write: - Source title — URL unavailable

Do NOT invent any source, URL, or domain.
"""
    ),
])

writer_chain = writer_prompt | llm | StrOutputParser()


# ── Critic chain ─────────────────────────────────────────────────────────────

critic_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a constructive research critic. "
        "Give structured, actionable feedback. Be specific, not vague. "
        "Keep each section to 2-3 sentences."
    ),
    (
        "human",
        """Review this research report carefully.

REPORT:
{report}

---

Output your review using EXACTLY this Markdown structure:

## Critic Review

**Score:** X / 10

### Completeness
Assess whether all important aspects of the topic are covered.

### Accuracy Concerns
Flag any claims that appear unverified, misleading, or unsupported.

### Missing Context
What important background, data, or perspective is absent?

### Potential Limitations
Comment on source quality, recency, or bias.

### Suggested Improvements
2-3 concrete suggestions to improve the report.

### Overall Assessment
One paragraph summary verdict.
"""
    ),
])

critic_chain = critic_prompt | llm | StrOutputParser()
