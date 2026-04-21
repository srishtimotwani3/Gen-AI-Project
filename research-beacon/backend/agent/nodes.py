import os
import re
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from .state import AgentState
from .tools import search_related_papers
from ..utils.pdf_parser import parse_pdf_bytes
from ..utils.url_parser import parse_url

# ── Model fallback chain ─────────────────────────────────────────────────────
# Each model has its own independent free-tier quota pool.
# Using explicit versioned names to avoid NOT_FOUND errors on the API.
MODEL_FALLBACK_CHAIN = [
    "gemini-2.0-flash",           # ~1,500 RPD free tier
    "gemini-2.0-flash-lite",      # lighter 2.0 variant, separate quota pool
    "gemini-1.5-flash-latest",    # ~1,500 RPD free tier
    "gemini-1.5-flash-8b-latest", # smallest/fastest, separate quota pool
]

def _is_daily_quota_exhausted(err_str: str) -> bool:
    """Daily RPD limit hit — skip to next model."""
    return (
        "GenerateRequestsPerDayPerProjectPerModel" in err_str
        or ("RESOURCE_EXHAUSTED" in err_str and "'limit': 0" in err_str)
        or ("RESOURCE_EXHAUSTED" in err_str and "limit: 0" in err_str)
    )

def _is_model_not_found(err_str: str) -> bool:
    """The specific model name doesn't exist in this API version — skip to next."""
    # Only match real 404 model-not-found, NOT broad "not found" strings
    # which could swallow API key permission errors
    return (
        "NOT_FOUND" in err_str
        and ("is not found for API version" in err_str or "not supported for generateContent" in err_str)
    )

def _is_api_not_enabled(err_str: str) -> bool:
    """True only for actual invalid API key or project API not enabled."""
    return (
        "API_KEY_INVALID" in err_str
        or "API key not valid" in err_str
        or ("PERMISSION_DENIED" in err_str and "generateContent" in err_str)
        or "not been enabled" in err_str
        or "SERVICE_DISABLED" in err_str
    )

def _is_rate_limited(err_str: str) -> bool:
    """Transient per-minute rate limit — short wait then retry."""
    return "RESOURCE_EXHAUSTED" in err_str or "429" in err_str

def _parse_retry_delay(err_str: str, default: int = 15) -> int:
    match = re.search(r"retryDelay.*?(\d+)s", err_str)
    return int(match.group(1)) + 2 if match else default

def invoke_with_fallback(messages, temperature: float = 0.3):
    """
    Try each model in MODEL_FALLBACK_CHAIN in order.
    Per-model behaviour:
      - Daily quota exhausted / model not found → skip immediately to next model.
      - Per-minute rate limit → wait the API-suggested delay, retry ONCE on the
        same model, then move to the next model (never crash the whole chain).
      - Invalid API key / API not enabled → fail immediately (no point trying others).
      - Any other unexpected error → fail immediately.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in the .env file.")

    for model_name in MODEL_FALLBACK_CHAIN:
        model = ChatGoogleGenerativeAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
        )
        print(f"[ResearchBeacon] Trying model: {model_name}")
        skip_to_next = False  # flag to break out of per_minute loop cleanly

        for per_minute_attempt in range(2):
            try:
                response = model.invoke(messages)
                print(f"[ResearchBeacon] ✓ Success with: {model_name}")
                return response

            except Exception as e:
                err_str = str(e)
                print(f"[ResearchBeacon] ✗ {model_name} (attempt {per_minute_attempt+1}): {err_str[:140]}")

                # ── Invalid API key / API not enabled → stop everything ──────
                if _is_api_not_enabled(err_str):
                    raise RuntimeError(
                        f"API key error: {err_str[:200]}\n\n"
                        "Check that:\n"
                        "1. GEMINI_API_KEY in .env is correct and the file is saved.\n"
                        "2. Generative Language API is enabled at console.cloud.google.com.\n"
                        "3. You restarted the server after changing .env."
                    )

                # ── Daily quota or model doesn't exist → try next model ──────
                if _is_daily_quota_exhausted(err_str) or _is_model_not_found(err_str):
                    print(f"[ResearchBeacon] {model_name}: daily quota/not-found, moving on...")
                    skip_to_next = True
                    break

                # ── Per-minute rate limit ────────────────────────────────────
                if _is_rate_limited(err_str):
                    if per_minute_attempt == 0:
                        wait = _parse_retry_delay(err_str, default=20)
                        print(f"[ResearchBeacon] {model_name}: per-minute limit, waiting {wait}s then retrying...")
                        time.sleep(wait)
                        continue  # retry once on the same model
                    else:
                        # Still rate-limited after retry → try next model
                        print(f"[ResearchBeacon] {model_name}: still rate-limited after retry, moving on...")
                        skip_to_next = True
                        break

                # ── Truly unexpected error (not quota-related) ───────────────
                raise

        if not skip_to_next:
            # Should not reach here normally (success returns early), but be safe
            break

    raise RuntimeError(
        "All Gemini models are quota-exhausted for today.\n"
        "• Quotas reset at midnight Pacific Time (~1:30 PM IST).\n"
        "• To use the app right now: go to console.cloud.google.com, enable billing "
        "on your project (costs ~$0.0001/request, effectively free for personal use)."
    )


def extract_text_node(state: AgentState) -> dict:
    """Extract text based on the source type."""
    if state.get("paper_text"):
        return state

    try:
        source_type = state["source_type"]
        source_ref = state["source_ref"]

        if source_type == "url":
            result = parse_url(source_ref)
            return {
                "paper_text": result["text"],
                "paper_title": result["title"],
                "paper_authors": "",
                "error": None
            }
        elif source_type == "pdf":
            pass

    except Exception as e:
        return {"error": f"Failed to extract text: {str(e)}"}

    return {}


def to_markdown(val) -> str:
    """
    Recursively convert any JSON value (str, list, dict) to clean markdown.
    Safety net in case the LLM ignores the "plain string" instruction.
    """
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        parts = []
        for item in val:
            s = to_markdown(item)
            if s:
                parts.append(s if s.startswith(("-", "*", "#")) else f"- {s}")
        return "\n".join(parts)
    if isinstance(val, dict):
        parts = []
        for k, v in val.items():
            heading = k.strip()
            if not heading.startswith("#"):
                heading = f"### {heading}"
            parts.append(heading)
            content = to_markdown(v)
            if content:
                parts.append(content)
        return "\n".join(parts)
    return str(val)


def analyze_paper_node(state: AgentState) -> dict:
    """
    Single LLM call that:
    1. Validates the document is a research paper.
    2. Extracts title, authors, and all analysis sections.
    """
    if state.get("error"):
        return {}

    prompt = f"""You are an expert academic research analyst. Your first task is to determine if the provided text is a genuine academic research paper.

A genuine research paper typically has: a clear research question or hypothesis, a methodology section, experimental results or findings, citations/references, and an abstract.

---

STEP 1 — CLASSIFICATION:
Read the text carefully. Decide if this is an academic research paper.
Set "is_research_paper" to true or false in your JSON output.

STEP 2 — ANALYSIS (only if is_research_paper is true):
If it IS a research paper, fill in all the remaining keys with detailed analysis.
If it is NOT a research paper, set all other keys to empty strings "".

---

CRITICAL FORMATTING RULES (for all string values):
1. Every value MUST be a plain STRING — not a nested JSON object, not an array, not a dict.
2. Use markdown subheadings with ### for organization within strings.
3. Use bullet points (- item) under each subheading. Keep bullets concise — 1 sentence each.
4. Do NOT use LaTeX. Use Unicode (α, β, θ, Σ, Δ) and <sub>/<sup> for math notation.
5. Use **bold** for key terms and `code` for model names/metrics.
6. Each analysis section: 2-3 subheadings, 2-3 bullets each.
7. No raw Python lists, curly braces, or array syntax in values.

---

JSON KEYS TO RETURN:

"is_research_paper": boolean (true or false)

"title": Exact paper title as a plain string. Empty string if not a research paper.

"authors": Comma-separated author names as they appear. "Authors not listed" if absent. Empty string if not a research paper.

"summary": Plain string with subheadings:
### Background & Motivation
- bullet
### Core Contribution
- bullet
### Results at a Glance
- bullet

"key_findings": Plain string with subheadings:
### Novel Contributions
- bullet
### Performance & Benchmarks
- bullet
### Broader Impact
- bullet

"methodology": Plain string with subheadings:
### Architecture & Model Design
- bullet
### Training & Optimization
- bullet
### Evaluation Protocol
- bullet

"limitations_future": Plain string with subheadings:
### Current Limitations
- bullet
### Future Research Directions
- bullet

"search_query": A single plain string (8-12 words) — precise semantic query to find papers using the SAME methodology, task domain, or model type. Focus on technical approach, not title keywords. Empty string if not a research paper.

---

Document Text (first 25000 chars):
{state['paper_text'][:25000]}
"""

    try:
        response = invoke_with_fallback([HumanMessage(content=prompt)])

        raw_content = response.content
        if isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "".join(text_parts).strip()
        else:
            content = str(raw_content).strip()

        # Strip markdown code fences
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        import json
        data = json.loads(content.strip())

        # Check research paper classification first
        is_research_paper = data.get("is_research_paper", True)
        if not is_research_paper:
            return {
                "error": "NOT_A_RESEARCH_PAPER"
            }

        title = to_markdown(data.get("title", ""))
        if not title or title.lower() == "unknown":
            title = state.get("paper_title", "")

        authors = to_markdown(data.get("authors", ""))

        return {
            "paper_title": title,
            "paper_authors": authors,
            "search_query": to_markdown(data.get("search_query", title)),
            "summary": to_markdown(data.get("summary", "No summary available.")),
            "key_findings": to_markdown(data.get("key_findings", "No key findings available.")),
            "methodology": to_markdown(data.get("methodology", "No methodology available.")),
            "limitations_future": to_markdown(data.get("limitations_future", "No limitations listed."))
        }

    except Exception as e:
        return {"error": f"Failed to analyze paper: {str(e)}"}


def related_papers_node(state: AgentState) -> dict:
    """Search for related papers and trim snippets in pure Python — no LLM call."""
    if state.get("error"):
        return {}

    query = state.get("search_query") or state.get("paper_title") or "Unknown paper"
    paper_title = state.get("paper_title", "").lower().strip()

    papers = search_related_papers(query)

    # Filter out the paper being analyzed itself, then trim snippets
    cleaned = []
    for p in papers:
        candidate_title = p.get("title", "").lower().strip()
        # Skip if title closely matches the analyzed paper
        if paper_title and (
            candidate_title == paper_title
            or paper_title in candidate_title
            or candidate_title in paper_title
        ):
            continue

        # Truncate snippet to ~2-3 concise sentences (max 280 chars)
        snippet = p.get("snippet", "")
        snippet = _truncate_to_sentences(snippet, max_chars=280)

        cleaned.append({
            "title": p.get("title", "Unknown Title"),
            "url": p.get("url", ""),
            "snippet": snippet
        })

    return {"related_papers": cleaned}


def _truncate_to_sentences(text: str, max_chars: int = 280) -> str:
    """Truncate text to fit within max_chars, preferring sentence boundaries."""
    if not text:
        return ""
    # Clean common LaTeX artifacts
    text = re.sub(r'start_POSTSUBSCRIPT|end_POSTSUBSCRIPT|DISPLAYSTYLE|math italic', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) <= max_chars:
        return text

    # Try to cut at a sentence boundary
    truncated = text[:max_chars]
    last_period = max(truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? '))
    if last_period > max_chars // 2:
        return truncated[:last_period + 1].strip()

    # Fall back to word boundary
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space].strip() + '…'

    return truncated.strip() + '…'


def qa_node(state: AgentState) -> dict:
    if state.get("error") or not state.get("qa_history"):
        return {}

    question = state["qa_history"][-1]["question"]

    prompt = f"""You are an expert research assistant. Based on the following research paper, answer the user's question clearly and concisely.
If the answer is not in the text, say so directly.

FORMATTING RULES:
- Do NOT use LaTeX. Use Unicode (α, β, θ) and HTML tags <sub>/<sup> for math.
- Use **bold** for key terms, bullet points for lists, clear paragraph breaks.
- Be thorough but focused — do not over-explain.

Paper Text:
{state['paper_text'][:30000]}

Question: {question}"""

    response = invoke_with_fallback([HumanMessage(content=prompt)])

    raw_content = response.content
    if isinstance(raw_content, list):
        text_parts = []
        for block in raw_content:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])
            elif isinstance(block, str):
                text_parts.append(block)
        answer_text = "".join(text_parts).strip()
    else:
        answer_text = str(raw_content).strip()

    history = state["qa_history"].copy()
    history[-1]["answer"] = answer_text

    return {"qa_history": history}
