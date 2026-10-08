"""PROVIDED - do not edit. Daytona sandbox for the agent (https://docs.langchain.com/oss/python/deepagents/sandboxes).

Usage:
    with open_sandbox() as backend:        # backend is a DaytonaSandbox: file tools + `execute` shell tool
        upload(backend, {"/tmp/work/x.py": b"print(1)"})
        agent = create_deep_agent(..., backend=backend)
        ...
        files = download(backend, ["/tmp/work/report/report.md"])

The sandbox is ALWAYS stopped and deleted on exit (sandboxes cost money until stopped).
Needs DAYTONA_API_KEY in the environment (.env). NEVER put secrets inside the sandbox: an agent that
reads attacker-controlled web text can be tricked into running commands there.
"""
import sys
from contextlib import contextmanager

from daytona import Daytona
from dotenv import load_dotenv
from langchain_daytona import DaytonaSandbox

load_dotenv()


@contextmanager
def open_sandbox():
    client = Daytona()  # reads DAYTONA_API_KEY
    box = client.create()
    try:
        yield DaytonaSandbox(sandbox=box)
    finally:
        for cleanup in (box.stop, lambda: client.delete(box)):
            try:
                cleanup()
            except Exception as exc:  # never hide the original error
                print(f"[sandbox] cleanup warning: {exc}", file=sys.stderr)


def upload(backend, files):
    """files: {absolute_path: bytes}. Seeds the sandbox before the agent runs."""
    backend.upload_files(list(files.items()))


def download(backend, paths):
    """Returns {absolute_path: bytes or None (missing/failed)}."""
    return {result.path: result.content for result in backend.download_files(paths)}
