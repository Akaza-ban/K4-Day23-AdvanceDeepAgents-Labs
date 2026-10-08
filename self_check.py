"""self_check.py - PROVIDED, do not edit.   Run it before you submit:   python self_check.py

It checks the AUTOMATIC parts of RUBRIC.md on YOUR reports/ folder, so you find problems before the grader does:
  * every topic of topics.md has a report (a reports/*.meta.json whose "topic" matches, case-insensitive) with its
    .md and .sources.json;
  * meta.json: subagent_calls >= 3 and at least 3 of the 4 source families (arxiv, hf-daily, hf-search, web);
  * YOUR check_citations.check() finds no problem in the report;
  * git: .env is not tracked and no tracked file contains something that looks like an API key.
Use `--no-git` to skip the git checks. It reads files only: no network, no LLM, no cost.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FAMILIES = {"arxiv", "hf-daily", "hf-search", "web"}
KEY_LIKE = re.compile(r"(sk-[A-Za-z0-9_\-]{20,}|(API_KEY|SECRET|TOKEN|PASSWORD)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,})")


def load_topics():
    return re.findall(r"^\d+\. (.+)$", (ROOT / "topics.md").read_text(encoding="utf-8"), re.M)


def find_meta(topic, reports):
    for path in sorted(reports.glob("*.meta.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if str(meta.get("topic", "")).strip().lower() == topic.strip().lower():
            return path, meta
    return None, None


def load_validator():
    try:
        sys.path.insert(0, str(ROOT))
        from check_citations import check
        return check
    except Exception as exc:  # noqa: BLE001
        return lambda report, sources: [f"cannot import check_citations.check: {exc}"]


def check_topic(topic, reports, validator):
    meta_path, meta = find_meta(topic, reports)
    if meta is None:
        return ["no report found (no reports/*.meta.json with this topic)"]
    stem = meta_path.name[: -len(".meta.json")]
    problems = []
    report_path, sources_path = reports / f"{stem}.md", reports / f"{stem}.sources.json"
    for path in (report_path, sources_path):
        if not path.exists():
            problems.append(f"missing {path.name}")
    if problems:
        return problems
    if int(meta.get("subagent_calls", 0)) < 3:
        problems.append(f"meta.json subagent_calls = {meta.get('subagent_calls', 0)} (need >= 3)")
    if len(FAMILIES & set(meta.get("source_families", []))) < 3:
        problems.append(f"only {len(FAMILIES & set(meta.get('source_families', [])))} source families in meta.json "
                        f"(need >= 3 of {sorted(FAMILIES)})")
    try:
        found = validator(report_path.read_text(encoding="utf-8"), json.loads(sources_path.read_text(encoding="utf-8")))
    except NotImplementedError:
        found = ["check_citations.check is not implemented yet"]
    except Exception as exc:  # noqa: BLE001
        found = [f"check_citations.check crashed: {type(exc).__name__}: {exc}"]
    problems += [f"citations: {p}" for p in found[:5]] + (["citations: ..."] if len(found) > 5 else [])
    return problems


def check_git():
    problems = []
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if tracked.returncode != 0:
        return ["this folder is not a git repository (git init, then commit, then push to a PUBLIC repo)"]
    files = tracked.stdout.splitlines()
    if ".env" in files:
        problems.append(".env is tracked by git: remove it (git rm --cached .env) and REVOKE the keys it contains")
    for name in files:
        if name == ".env.example" or name.endswith((".png", ".jpg", ".pdf")):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if KEY_LIKE.search(text):
            problems.append(f"{name}: contains something that looks like an API key")
    return problems


def main(argv):
    reports = ROOT / "reports"
    validator = load_validator()
    failed = False
    print("topic".ljust(60), "result")
    for topic in load_topics():
        problems = check_topic(topic, reports, validator)
        failed |= bool(problems)
        print(topic[:58].ljust(60), "OK" if not problems else "PROBLEMS")
        for problem in problems:
            print("    -", problem)
    if "--no-git" not in argv:
        problems = check_git()
        failed |= bool(problems)
        print("git / secrets".ljust(60), "OK" if not problems else "PROBLEMS")
        for problem in problems:
            print("    -", problem)
    print("\nREADY to submit (the manual parts of RUBRIC.md are still graded by a person)." if not failed
          else "\nNOT ready: fix the problems above.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
