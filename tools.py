"""tools.py - STUDENT IMPLEMENTS.  Source tools for the research agents.   Guide: GUIDE.md, part 1.

Rules for every tool:
  * runs on the HOST (not in the sandbox): API keys must never enter the sandbox;
  * returns a STRING (JSON text of compact records) and NEVER raises:
        "NO RESULTS"  when the source answers with nothing,
        "ERROR: ..."  when the source keeps failing after the retries (the agent then tries another source);
  * the docstring is the tool description the LLM reads: keep it precise (what it does, what it returns, when to use it).
Try your tools without any agent:   python tools.py
"""
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

# ---- constants (given) ----
ARXIV_URL = "https://export.arxiv.org/api/query"  # https only: http answers 301
HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
HF_SEARCH_URL = "https://huggingface.co/api/papers/search"
EXA_URL = "https://mcp.exa.ai/mcp"

_last_arxiv_time = 0.0


class RetryableError(Exception):
    """Given. Raise it inside a call to ask with_retry to wait and try again (retry_after in seconds, optional)."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


# ---- TODO 1: retry helper ----
def with_retry(fn, *, attempts=5, base=1.0, cap=30.0):
    """Call fn(); when it raises RetryableError or temporary network/HTTP errors, wait and call it again."""
    for attempt in range(attempts):
        try:
            return fn()
        except (RetryableError, httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == attempts - 1:
                raise

            retry_after = None
            if isinstance(exc, RetryableError) and exc.retry_after is not None:
                retry_after = exc.retry_after
            elif isinstance(exc, httpx.HTTPStatusError):
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                raw_ra = exc.response.headers.get("Retry-After")
                if raw_ra:
                    try:
                        retry_after = float(raw_ra)
                    except (ValueError, TypeError):
                        pass

            if retry_after is not None:
                delay = min(cap, max(0.5, float(retry_after)))
            else:
                backoff = min(cap, base * (2 ** attempt))
                delay = backoff + random.uniform(0.1, 0.5 * backoff)
                delay = min(cap, delay)

            time.sleep(delay)


# ---- TODO 2: arXiv ----
@tool
def arxiv_search(query: str, max_results: int = 10) -> str:
    """Search arXiv papers by keywords, newest first. Returns a JSON list of {id, url, published, title, summary}."""
    global _last_arxiv_time
    try:
        terms = [w for w in re.findall(r"[\w-]+", query) if w]
        if not terms:
            return "NO RESULTS"

        # arXiv etiquette: at least 3 seconds between two calls
        elapsed = time.time() - _last_arxiv_time
        if elapsed < 3.0:
            time.sleep(3.0 - elapsed)
        _last_arxiv_time = time.time()

        max_results_clamped = max(1, min(int(max_results), 30))
        search_query = " AND ".join(f"all:{t}" for t in terms)

        def _fetch():
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    ARXIV_URL,
                    params={
                        "search_query": search_query,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                        "max_results": max_results_clamped,
                    },
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    ra = None
                    if "Retry-After" in resp.headers:
                        try:
                            ra = float(resp.headers["Retry-After"])
                        except (ValueError, TypeError):
                            pass
                    raise RetryableError(f"arXiv HTTP {resp.status_code}", retry_after=ra)
                resp.raise_for_status()
                return resp.text

        xml_text = with_retry(_fetch, attempts=6, base=2.0, cap=60.0)

        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            return "NO RESULTS"

        records = []
        for entry in entries:
            raw_id = (entry.find("atom:id", ns).text or "").strip()
            clean_id = raw_id.split("/abs/")[-1]
            clean_id = re.sub(r"v\d+$", "", clean_id)
            if not clean_id:
                continue

            pub_elem = entry.find("atom:published", ns)
            published = (pub_elem.text or "").strip()[:10] if pub_elem is not None else ""

            title_elem = entry.find("atom:title", ns)
            title = " ".join((title_elem.text or "").split()) if title_elem is not None else "Untitled"

            sum_elem = entry.find("atom:summary", ns)
            summary = " ".join((sum_elem.text or "").split())[:600] if sum_elem is not None else ""

            records.append({
                "id": clean_id,
                "url": f"https://arxiv.org/abs/{clean_id}",
                "published": published,
                "title": title,
                "summary": summary,
            })

        if not records:
            return "NO RESULTS"
        return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ---- TODO 3: Hugging Face ----
@tool
def hf_daily_papers(limit: int = 30, date: str = "", keyword: str = "") -> str:
    """Hugging Face Daily Papers = what is trending in AI research. Returns a JSON list of
    {id, url, published, title, summary, upvotes, github, stars} sorted by upvotes. `date` is YYYY-MM-DD (empty = latest).
    `keyword` filters title/summary; there is no topic search on this endpoint (use hf_search_papers for a topic)."""
    try:
        limit_clamped = max(1, min(int(limit), 100))
        params = {"limit": limit_clamped}
        if date:
            params["date"] = date.strip()

        def _fetch():
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(HF_DAILY_URL, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    ra = None
                    if "Retry-After" in resp.headers:
                        try:
                            ra = float(resp.headers["Retry-After"])
                        except (ValueError, TypeError):
                            pass
                    raise RetryableError(f"HF Daily HTTP {resp.status_code}", retry_after=ra)
                resp.raise_for_status()
                return resp.json()

        items = with_retry(_fetch, attempts=5, base=1.0, cap=30.0)
        if not isinstance(items, list) or not items:
            return "NO RESULTS"

        records = []
        for item in items:
            paper = item.get("paper") if isinstance(item.get("paper"), dict) else item
            paper_id = paper.get("id") or item.get("id")
            if not paper_id:
                continue

            published = (paper.get("publishedAt") or item.get("publishedAt") or "")[:10]
            title = " ".join((paper.get("title") or item.get("title") or "").split())
            summary = " ".join((paper.get("summary") or item.get("summary") or "").split())[:600]
            upvotes = int(paper.get("upvotes") or item.get("upvotes") or 0)
            github = paper.get("githubRepo") or item.get("githubRepo") or ""
            stars = int(paper.get("githubStars") or item.get("githubStars") or 0)

            records.append({
                "id": paper_id,
                "url": f"https://huggingface.co/papers/{paper_id}",
                "published": published,
                "title": title,
                "summary": summary,
                "upvotes": upvotes,
                "github": github,
                "stars": stars,
            })

        if keyword:
            kw = keyword.lower().strip()
            records = [r for r in records if kw in (r["title"] + " " + r["summary"]).lower()]

        records.sort(key=lambda r: r["upvotes"], reverse=True)

        if not records:
            return "NO RESULTS"
        return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


@tool
def hf_search_papers(query: str, limit: int = 10) -> str:
    """Search Hugging Face papers by topic. Returns a JSON list of
    {id, url, published, title, summary, upvotes, github, stars}."""
    try:
        limit_clamped = max(1, min(int(limit), 50))
        params = {"q": query.strip(), "limit": limit_clamped}

        def _fetch():
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(HF_SEARCH_URL, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    ra = None
                    if "Retry-After" in resp.headers:
                        try:
                            ra = float(resp.headers["Retry-After"])
                        except (ValueError, TypeError):
                            pass
                    raise RetryableError(f"HF Search HTTP {resp.status_code}", retry_after=ra)
                resp.raise_for_status()
                return resp.json()

        items = with_retry(_fetch, attempts=5, base=1.0, cap=30.0)
        if not isinstance(items, list) or not items:
            return "NO RESULTS"

        records = []
        for item in items:
            paper = item.get("paper") if isinstance(item.get("paper"), dict) else item
            paper_id = paper.get("id") or item.get("id")
            if not paper_id:
                continue

            published = (paper.get("publishedAt") or item.get("publishedAt") or "")[:10]
            title = " ".join((paper.get("title") or item.get("title") or "").split())
            raw_summary = paper.get("ai_summary") or paper.get("summary") or item.get("summary") or ""
            summary = " ".join(raw_summary.split())[:600]
            upvotes = int(paper.get("upvotes") or item.get("upvotes") or 0)
            github = paper.get("githubRepo") or item.get("githubRepo") or ""
            stars = int(paper.get("githubStars") or item.get("githubStars") or 0)

            records.append({
                "id": paper_id,
                "url": f"https://huggingface.co/papers/{paper_id}",
                "published": published,
                "title": title,
                "summary": summary,
                "upvotes": upvotes,
                "github": github,
                "stars": stars,
            })

        if not records:
            return "NO RESULTS"
        return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ---- TODO 4: web search / fetch through the Exa MCP endpoint ----
def _call_exa_mcp(tool_name: str, arguments: dict) -> str:
    """Invoke an Exa MCP tool over HTTP JSON-RPC with SSE response handling."""
    api_key = (os.getenv("EXA_API_KEY") or "").strip()
    endpoint = f"{EXA_URL}?exaApiKey={api_key}" if api_key else EXA_URL

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    def _post():
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                endpoint,
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                ra = None
                if "Retry-After" in resp.headers:
                    try:
                        ra = float(resp.headers["Retry-After"])
                    except (ValueError, TypeError):
                        pass
                raise RetryableError(f"Exa HTTP {resp.status_code}", retry_after=ra)
            resp.raise_for_status()

            # Parse Server-Sent Events (SSE)
            texts = []
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    raw_data = line[len("data:"):].strip()
                    if not raw_data:
                        continue
                    try:
                        data = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        err_obj = data["error"]
                        err_msg = err_obj.get("message", str(err_obj))
                        if "rate" in err_msg.lower() and "limit" in err_msg.lower():
                            raise RetryableError("Exa rate limit flag", retry_after=20.0)
                        raise RuntimeError(f"Exa RPC error: {err_msg}")

                    res = data.get("result", {})
                    meta = res.get("_meta", {})
                    # Detect Exa free tier rate limit flag in _meta
                    if any("rate" in str(k).lower() and "limit" in str(k).lower() for k in meta.keys()):
                        raise RetryableError("Exa rate limited (_meta)", retry_after=20.0)
                    if any("rate" in str(v).lower() and "limit" in str(v).lower() for v in meta.values()):
                        raise RetryableError("Exa rate limited (_meta values)", retry_after=20.0)

                    content_list = res.get("content", [])
                    for c in content_list:
                        if isinstance(c, dict) and c.get("type") == "text":
                            t = c.get("text", "")
                            # Check if body text contains rate limit announcement
                            if "rate limit" in t.lower() and ("exceeded" in t.lower() or "try again" in t.lower()):
                                raise RetryableError("Exa rate limit text", retry_after=20.0)
                            texts.append(t)

            combined = "\n\n".join(texts).strip()
            return combined

    try:
        result_text = with_retry(_post, attempts=5, base=2.0, cap=60.0)
        if not result_text:
            return "NO RESULTS"
        return result_text
    except Exception as exc:
        err = f"ERROR: {type(exc).__name__}: {exc}"
        if api_key:
            err = err.replace(api_key, "[REDACTED]")
        return err


@tool
def web_search(query: str, objective: str = "", num_results: int = 5) -> str:
    """Search the web (Exa). Describe the ideal page in natural language. Returns clean text of the top results with URLs."""
    obj = objective.strip() if objective else f"Find authoritative research papers, surveys, and technical blogs about {query}"
    num_clamped = max(1, min(int(num_results), 20))
    return _call_exa_mcp("web_search_exa", {"query": query, "objective": obj, "numResults": num_clamped})


@tool
def web_fetch(url: str) -> str:
    """Read the full content of one web page (e.g. an arXiv abstract page) as markdown. Long pages are truncated."""
    res = _call_exa_mcp("web_fetch_exa", {"urls": [url]})
    if res.startswith("ERROR:"):
        return res
    if len(res) > 12000:
        res = res[:12000] + "\n\n... [Content truncated at 12000 chars]"
    return res


# ---- TODO 5: registry (the researcher subagent gets exactly these) ----
SOURCE_TOOLS = [arxiv_search, hf_daily_papers, hf_search_papers, web_search, web_fetch]


if __name__ == "__main__":
    for name, fn, args in [
        ("arxiv_search", arxiv_search, {"query": "world model", "max_results": 3}),
        ("hf_daily_papers", hf_daily_papers, {"limit": 20}),
        ("hf_search_papers", hf_search_papers, {"query": "world model", "limit": 3}),
        ("web_search", web_search, {"query": "survey paper on world models", "num_results": 2}),
        ("web_fetch", web_fetch, {"url": "https://arxiv.org/abs/1803.10122"}),
    ]:
        try:
            print(f"== {name}\n{fn.invoke(args)[:400]}\n")
        except NotImplementedError as exc:
            print(f"== {name}: not implemented yet ({exc})\n")
