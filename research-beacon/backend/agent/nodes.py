import os
import re
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from .state import AgentState
from .tools import search_related_papers
from ..utils.pdf_parser import parse_pdf_bytes
from ..utils.url_parser import parse_url

# ── Groq models (tried first — generous free tier, very fast) ────────────────
GROQ_MODEL_CHAIN = [
    "llama-3.3-70b-versatile",   # 32K context, 14,400 RPD free
    "llama-3.1-8b-instant",      # 128K context, 14,400 RPD free — separate pool
]

# ── Gemini fallback chain (used only if ALL Groq models are exhausted) ───────
GEMINI_MODEL_CHAIN = [
    "gemini-2.0-flash",           # ~1,500 RPD free tier
    "gemini-2.0-flash-lite",      # lighter 2.0 variant, separate quota pool
    "gemini-1.5-flash-latest",    # ~1,500 RPD free tier
    "gemini-1.5-flash-8b-latest", # smallest/fastest, separate quota pool
]

# ── Error classifier helpers ──────────────────────────────────────────────────

def _is_daily_quota_exhausted(err_str: str) -> bool:
    """Daily RPD limit hit — skip to next model."""
    return (
        "GenerateRequestsPerDayPerProjectPerModel" in err_str
        or "rate_limit_exceeded" in err_str.lower()
        or "daily" in err_str.lower() and "limit" in err_str.lower()
        or ("RESOURCE_EXHAUSTED" in err_str and "'limit': 0" in err_str)
        or ("RESOURCE_EXHAUSTED" in err_str and "limit: 0" in err_str)
    )

def _is_model_not_found(err_str: str) -> bool:
    """The specific model name doesn't exist — skip to next."""
    return (
        "NOT_FOUND" in err_str
        and ("is not found for API version" in err_str or "not supported for generateContent" in err_str)
    ) or "model not found" in err_str.lower()

def _is_api_not_enabled(err_str: str) -> bool:
    """Invalid API key or project API not enabled — stop everything."""
    return (
        "API_KEY_INVALID" in err_str
        or "API key not valid" in err_str
        or ("PERMISSION_DENIED" in err_str and "generateContent" in err_str)
        or "not been enabled" in err_str
        or "SERVICE_DISABLED" in err_str
        or "invalid_api_key" in err_str.lower()
        or "authentication" in err_str.lower() and "failed" in err_str.lower()
    )

def _is_rate_limited(err_str: str) -> bool:
    """Transient per-minute / per-second rate limit — short wait then retry."""
    return (
        "RESOURCE_EXHAUSTED" in err_str
        or "429" in err_str
        or "too_many_requests" in err_str.lower()
        or "tokens per" in err_str.lower()
    )

def _is_context_too_long(err_str: str) -> bool:
    """Input exceeds the model's context window — skip to a larger-context model."""
    return (
        "context_length_exceeded" in err_str.lower()
        or "maximum context length" in err_str.lower()
        or "Request too large" in err_str
    )

def _parse_retry_delay(err_str: str, default: int = 15) -> int:
    match = re.search(r"retryDelay.*?(\d+)s", err_str)
    if match:
        return int(match.group(1)) + 2
    # Groq often gives "Please try again in Xs"
    match2 = re.search(r"try again in ([\d.]+)s", err_str)
    if match2:
        return int(float(match2.group(1))) + 2
    return default


def _try_model_chain(chain_models, build_model_fn, messages):
    """
    Generic helper: iterate over a list of model names, calling build_model_fn(name)
    to create the LangChain model object. Returns the response on first success.
    Returns None if ALL models in the chain are quota-exhausted/not-found.
    Raises immediately on invalid-key or unexpected errors.
    """
    for model_name in chain_models:
        model = build_model_fn(model_name)
        print(f"[ResearchBeacon] Trying model: {model_name}")
        skip_to_next = False

        for attempt in range(2):
            try:
                response = model.invoke(messages)
                print(f"[ResearchBeacon] [OK] Success with: {model_name}")
                return response

            except Exception as e:
                err_str = str(e)
                print(f"[ResearchBeacon] [FAIL] {model_name} (attempt {attempt+1}): {err_str[:160]}")

                if _is_api_not_enabled(err_str):
                    raise  # propagate key errors immediately

                if _is_daily_quota_exhausted(err_str) or _is_model_not_found(err_str) or _is_context_too_long(err_str):
                    print(f"[ResearchBeacon] {model_name}: quota/not-found/context, moving on...")
                    skip_to_next = True
                    break

                if _is_rate_limited(err_str):
                    if attempt == 0:
                        wait = _parse_retry_delay(err_str, default=20)
                        print(f"[ResearchBeacon] {model_name}: rate-limited, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"[ResearchBeacon] {model_name}: still rate-limited, moving on...")
                        skip_to_next = True
                        break

                raise  # unexpected error

        if not skip_to_next:
            break

    return None  # all models in this chain exhausted


def invoke_with_fallback(messages, temperature: float = 0.3):
    """
    Primary: try Groq models (fast, generous free tier).
    Fallback: try Gemini models if all Groq models are quota-exhausted.
    Raises a clear RuntimeError if every model in both chains is exhausted.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    # ── 1. Try Groq first ────────────────────────────────────────────────────
    if groq_key:
        def build_groq(name):
            return ChatGroq(model=name, api_key=groq_key, temperature=temperature)

        result = _try_model_chain(GROQ_MODEL_CHAIN, build_groq, messages)
        if result is not None:
            return result
        print("[ResearchBeacon] All Groq models exhausted, switching to Gemini...")
    else:
        print("[ResearchBeacon] GROQ_API_KEY not set, skipping Groq and using Gemini directly.")

    # ── 2. Fall back to Gemini ────────────────────────────────────────────────
    if not gemini_key:
        raise RuntimeError(
            "Neither GROQ_API_KEY nor GEMINI_API_KEY is configured in .env.\n"
            "Add at least one of them and restart the server."
        )

    def build_gemini(name):
        return ChatGoogleGenerativeAI(model=name, api_key=gemini_key, temperature=temperature)

    result = _try_model_chain(GEMINI_MODEL_CHAIN, build_gemini, messages)
    if result is not None:
        return result

    raise RuntimeError(
        "All LLM models are quota-exhausted.\n"
        "• Groq free tier: 14,400 requests/day — resets daily at midnight UTC.\n"
        "• Gemini free tier: ~1,500 requests/day — resets at midnight Pacific (~1:30 PM IST).\n"
        "• Add a GROQ_API_KEY to .env for a much larger free quota (see README for setup guide)."
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
        # Instead of failing with a raw HTTP error, gracefully reject as not a research paper
        return {"error": "NOT_A_RESEARCH_PAPER"}

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
4. Do NOT use LaTeX. Use Unicode (α, β, θ, Σ, Δ, ², ³) for math notation. Do NOT use HTML tags like <sub> or <sup>. Preserve regular numbers accurately; do NOT convert regular numbers or citations into superscripts.
5. Use **bold** for key terms and `code` for model names/metrics.
6. Each analysis section: 2-3 subheadings, 2-3 bullets each.
7. No raw Python lists, curly braces, or array syntax in values.
8. CRITICAL: Your output MUST be strictly valid JSON. Any double quotes inside the text values MUST be escaped as \\" or replaced with single quotes ('').

---

JSON KEYS TO RETURN:

"is_research_paper": boolean (true or false)

"title": Exact paper title as a plain string. Empty string if not a research paper.

"authors": Comma-separated author names as they appear. IMPORTANT: Clean up and fix any weird letter spacing from the raw text (e.g., turn 'A s h i s h' into 'Ashish'). "Authors not listed" if absent. Empty string if not a research paper.

"summary": Plain string with subheadings. Do NOT use double quotes inside this text (use single quotes instead):
### Background & Motivation
- bullet
### Core Contribution
- bullet
### Results at a Glance
- bullet

"key_findings": Plain string with subheadings. Do NOT use double quotes inside this text (use single quotes instead):
### Novel Contributions
- bullet
### Performance & Benchmarks
- bullet
### Broader Impact
- bullet

"methodology": Plain string with subheadings. Do NOT use double quotes inside this text (use single quotes instead):
### Architecture & Model Design
- bullet
### Training & Optimization
- bullet
### Evaluation Protocol
- bullet

"limitations_future": Plain string with subheadings. Do NOT use double quotes inside this text (use single quotes instead):
### Current Limitations
- bullet
### Future Research Directions
- bullet

"search_query": A single plain string (8-12 words) — precise semantic query to find papers using the SAME methodology, task domain, or model type. Focus on technical approach, not title keywords. Empty string if not a research paper.

---

Document Text (first 18000 chars):
{state['paper_text'][:18000]}
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
        import re
        try:
            # Try parsing directly first
            data = json.loads(content.strip(), strict=False)
        except json.JSONDecodeError:
            # If that fails, extract just the JSON dictionary block using regex
            match = re.search(r'\{.*\}', content.strip(), re.DOTALL)
            if match:
                cleaned_content = match.group(0)
                # Strip control characters
                cleaned_content = re.sub(r'[\x00-\x1f]', '', cleaned_content)
                data = json.loads(cleaned_content, strict=False)
            else:
                raise ValueError("Could not extract JSON object from response")

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
    """Search for related papers and use LLM to beautifully format snippets."""
    if state.get("error"):
        return {}

    query = state.get("search_query") or state.get("paper_title") or "Unknown paper"
    paper_title = state.get("paper_title", "").lower().strip()

    papers = search_related_papers(query, limit=6)

    source_ref = state.get("source_ref", "").lower().strip()
    # Filter out the paper being analyzed itself using a more robust word-overlap check
    candidates = []
    paper_words = set(paper_title.replace('-', ' ').split())
    for p in papers:
        candidate_title = p.get("title", "").lower().strip()
        candidate_url = p.get("url", "").lower().strip()
        candidate_words = set(candidate_title.replace('-', ' ').split())
        
        # Filter if the source filename/url matches the candidate url
        if source_ref and source_ref != "qa" and source_ref in candidate_url:
            continue
            
        # If there's a strong word overlap, it's likely the same paper
        if paper_title:
            intersection = paper_words.intersection(candidate_words)
            if len(intersection) >= max(3, len(paper_words) - 2):
                continue
            if paper_title in candidate_title or candidate_title in paper_title:
                continue
        candidates.append(p)
        
    if not candidates:
        return {"related_papers": []}
        
    # Ask LLM to rewrite and format the snippets
    prompt = f"""You are an expert research editor. I will provide you with a list of related research papers and their raw, often messy snippets (which may contain garbage MathJax or duplicated text like O(n2)O(n^2)).
    
Your task is to return a clean JSON array of the top 3 to 4 related papers.
For each paper, clean up the snippet so that:
1. It is MAXIMUM 2 to 2.5 lines long (STRICTLY 20-30 words maximum). Do NOT exceed this length under any circumstances.
2. All formulas, time complexities, and math notations are formatted PERFECTLY using ONLY Unicode. Do NOT use HTML tags like <sub> or <sup>. Do NOT use LaTeX or markdown math. For example, use O(n²) instead of O(n2). Preserve regular numbers and citations as normal text.
3. The snippet accurately describes the paper based on the messy input.
4. Do NOT change, shorten, or summarize the "title" field, EXCEPT if the raw title is just a filename (e.g., ends with .pdf). If it's a filename, you MUST replace it with the ACTUAL academic title of that research paper. Otherwise, use the EXACT original title.
5. CRITICAL: Do NOT include the paper "{state.get('paper_title', '')}" in your output. That is the paper being analyzed, and must not be in the related papers list.

Return ONLY a JSON array of objects. No markdown formatting, no code blocks, just the JSON array.
Format:
[
  {{"title": "Paper Title", "url": "https...", "snippet": "Cleaned, beautifully formatted 2-line description..."}}, ...
]

Raw Papers:
{str(candidates[:6])}
"""
    try:
        response = invoke_with_fallback([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list):
            content = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
        
        # Strip code blocks
        if content.strip().startswith("```json"):
            content = content.strip()[7:]
        elif content.strip().startswith("```"):
            content = content.strip()[3:]
        if content.strip().endswith("```"):
            content = content.strip()[:-3]
            
        import json
        import re
        try:
            cleaned_papers = json.loads(content.strip(), strict=False)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', content.strip(), re.DOTALL)
            if match:
                cleaned_papers = json.loads(re.sub(r'[\x00-\x1f]', '', match.group(0)), strict=False)
            else:
                cleaned_papers = candidates[:4] # fallback to raw
                
        # Fallback slice just in case LLM returns more than 4
        return {"related_papers": cleaned_papers[:4]}
    except Exception as e:
        print(f"[ResearchBeacon] LLM cleaning failed for related papers: {e}")
        # Absolute fallback to raw
        return {"related_papers": candidates[:4]}


def qa_node(state: AgentState) -> dict:
    if state.get("error") or not state.get("qa_history"):
        return {}

    question = state["qa_history"][-1]["question"]

    prompt = f"""You are an expert research assistant. Based on the following research paper, answer the user's question clearly and concisely.
If the answer is not in the text, say so directly.

FORMATTING RULES:
- Do NOT use LaTeX. Use Unicode (α, β, θ, ², ³) for math notation. Do NOT use HTML tags like <sub> or <sup>.
- Use **bold** for key terms, bullet points for lists, clear paragraph breaks.
- Be thorough but focused — do not over-explain.

Paper Text (excerpt):
{state['paper_text'][:20000]}

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
