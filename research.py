"""research.py - STUDENT IMPLEMENTS.  The main script.   Guide: GUIDE.md, part 3.

Usage:  python research.py "survey about world model"
Result: reports/<slug>.md   reports/<slug>.sources.json   reports/<slug>.meta.json
"""
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

from agents import (
    FINALIZER_PATH,
    NOTES_DIR,
    REPORT_PATH,
    SOURCES_PATH,
    VALIDATOR_PATH,
    WORKDIR,
    build_lead_agent,
)
from model import make_model
from sandbox import download, open_sandbox, upload

ROOT = Path(__file__).parent
REPORTS = ROOT / "reports"
VALIDATOR_SOURCE = ROOT / "check_citations.py"
FINALIZER_SOURCE = ROOT / "finalize_citations.py"   # provided: uploaded next to your validator


def slugify(topic):
    """Turn a topic into a safe file name: lower case, runs of non-word characters become one "-", max 60 chars,
    never empty (fall back to "topic"). The topic is user input: "../../x" must not escape reports/."""
    clean = re.sub(r"[^\w]+", "-", str(topic).strip().lower()).strip("-")
    clean = clean[:60].rstrip("-")
    return clean or "topic"


def build_prompt(topic):
    """The user message sent to the lead agent."""
    return (
        f"Please conduct an extensive, multi-agent literature research and produce a comprehensive survey report "
        f"on the following topic: '{topic}'.\n\n"
        f"Follow all instructions in your system prompt strictly:\n"
        f"1. Plan and divide this topic into at least 3-4 independent sub-questions using `write_todos`.\n"
        f"2. Delegate each sub-question to the `researcher` subagent with `task` (make at least 3 subagent delegations).\n"
        f"3. Gather notes in {NOTES_DIR} and consolidate valid sources into EXACTLY {SOURCES_PATH} using `write_file`.\n"
        f"   CRITICAL: Ensure at least 3 distinct source families (out of arxiv, hf-daily, hf-search, web) are present.\n"
        f"4. Write the synthesis report body to EXACTLY {REPORT_PATH} using `write_file` according to REPORT_TEMPLATE.md.\n"
        f"   Do NOT write the '## References' section manually.\n"
        f"5. Run {FINALIZER_PATH} via `execute` to generate references and renumber citations.\n"
        f"6. Run {VALIDATOR_PATH} via `execute` to ensure all citations resolve (must print OK).\n"
        f"7. Have `citation-checker` spot-check key claims."
    )


def summarize(messages, elapsed, model_name):
    """Return {"model", "elapsed_s", "subagent_calls", "tool_calls": {name: count}, "tokens": {"input", "output"}}.

    PSEUDO-CODE: walk the lead's messages; for every message with tool_calls count call["name"] (subagent_calls = the
    count of "task"); add the input/output token counts from each message's usage_metadata when present.
    (Lead messages only: subagent tokens are not included, so this undercounts the real cost.)
    elapsed_s rounded to 0.1.
    """
    tool_counts = Counter()
    in_tokens = 0
    out_tokens = 0

    for msg in messages:
        # Extract tool calls
        t_calls = []
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            t_calls = msg.tool_calls
        elif isinstance(msg, dict) and "tool_calls" in msg:
            t_calls = msg.get("tool_calls") or []

        for tc in t_calls:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", str(tc))
            if name:
                tool_counts[name] += 1

        # Extract token usage metadata
        usage = getattr(msg, "usage_metadata", None)
        if not usage and isinstance(msg, dict):
            usage = msg.get("usage_metadata")
        if usage:
            if isinstance(usage, dict):
                in_tokens += usage.get("input_tokens") or usage.get("prompt_tokens") or 0
                out_tokens += usage.get("output_tokens") or usage.get("completion_tokens") or 0
            else:
                in_tokens += getattr(usage, "input_tokens", 0)
                out_tokens += getattr(usage, "output_tokens", 0)

    subagent_calls = tool_counts.get("task", 0)

    return {
        "model": model_name,
        "elapsed_s": round(float(elapsed), 1),
        "subagent_calls": subagent_calls,
        "tool_calls": dict(tool_counts),
        "tokens": {
            "input": in_tokens,
            "output": out_tokens,
        },
    }


def save_outputs(backend, topic, messages, elapsed, model_name, reports_dir=REPORTS):
    """Download the report from the sandbox and write the three files into reports_dir. Return the report path.

    PSEUDO-CODE:
      files = download(backend, [REPORT_PATH, SOURCES_PATH])
      if the report is missing/empty or sources.json is missing/invalid JSON: raise RuntimeError and WRITE NOTHING
          (a failed run must never leave an empty or half-written report behind)
      write <slug>.sources.json, <slug>.meta.json (topic + summarize(...) + n_sources + source_families: the sorted
      distinct "source" values of sources.json) and <slug>.md
    """
    files = download(backend, [REPORT_PATH, SOURCES_PATH])

    report_bytes = files.get(REPORT_PATH)
    if not report_bytes or not report_bytes.strip():
        # Fallback: check alternative paths if agent placed report elsewhere in /tmp/work
        res = backend.execute("find /tmp/work -maxdepth 3 -name '*.md' ! -path '*/notes/*'")
        for candidate in (res.output or "").splitlines():
            cand = candidate.strip()
            if cand.endswith(".md"):
                cand_bytes = download(backend, [cand]).get(cand)
                if cand_bytes and len(cand_bytes.strip()) > 300:
                    report_bytes = cand_bytes
                    break
        if not report_bytes or not report_bytes.strip():
            raise RuntimeError("Report is missing or empty in sandbox")

    sources_bytes = files.get(SOURCES_PATH)
    if not sources_bytes or not sources_bytes.strip():
        # Fallback: check alternative paths for sources.json
        res_s = backend.execute("find /tmp/work -maxdepth 3 -name '*sources*.json'")
        for candidate in (res_s.output or "").splitlines():
            cand = candidate.strip()
            if cand.endswith(".json"):
                cand_bytes = download(backend, [cand]).get(cand)
                if cand_bytes and cand_bytes.strip():
                    try:
                        parsed = json.loads(cand_bytes.decode("utf-8"))
                        if isinstance(parsed, list) and len(parsed) > 0:
                            sources_bytes = cand_bytes
                            break
                    except Exception:
                        pass
        if not sources_bytes or not sources_bytes.strip():
            raise RuntimeError("sources.json is missing or empty in sandbox")

    try:
        sources = json.loads(sources_bytes.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"sources.json is invalid JSON: {exc}")

    if not isinstance(sources, list) or not sources:
        raise RuntimeError("sources.json must be a non-empty list of source entries")

    n_sources = len(sources)
    source_families = sorted(list({
        str(s.get("source")).strip()
        for s in sources
        if isinstance(s, dict) and s.get("source")
    }))

    meta = {
        "topic": topic,
        **summarize(messages, elapsed, model_name),
        "n_sources": n_sources,
        "source_families": source_families,
    }

    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)
    report_file = reports_dir / f"{slug}.md"
    sources_file = reports_dir / f"{slug}.sources.json"
    meta_file = reports_dir / f"{slug}.meta.json"

    report_file.write_bytes(report_bytes)
    sources_file.write_bytes(sources_bytes)
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return report_file


def main(topic):
    """Return the process exit code (0 ok, 1 failed run, 2 no topic)."""
    topic = str(topic).strip()
    if not topic:
        print("Usage: python research.py \"<topic>\"", file=sys.stderr)
        return 2

    model = make_model()
    model_name = os.getenv("LAB_MODEL") or getattr(model, "model_name", "unknown")
    start = time.monotonic()

    with open_sandbox() as backend:
        # Create directories in sandbox
        backend.execute(f"mkdir -p {WORKDIR}/research/notes {WORKDIR}/report")

        # Upload validator and finalizer scripts
        upload(backend, {
            VALIDATOR_PATH: VALIDATOR_SOURCE.read_bytes(),
            FINALIZER_PATH: FINALIZER_SOURCE.read_bytes(),
        })

        agent = build_lead_agent(backend, model)
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": build_prompt(topic)}]},
                config={"recursion_limit": 1000},
            )
            messages = result.get("messages", []) if isinstance(result, dict) else []
            elapsed = time.monotonic() - start
            saved_report = save_outputs(backend, topic, messages, elapsed, model_name)
            print(f"SUCCESS: Report saved to {saved_report}")
            return 0
        except Exception as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:])))
