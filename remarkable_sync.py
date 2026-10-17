#!/usr/bin/env python3
"""
reMarkable weekly sync.

Walks the reMarkable cloud, and for every handwritten notebook that is NEW or
EDITED since the last run, renders it to a PDF and writes it under OUTPUT_DIR,
in a subfolder chosen by FOLDER_MAP. Meant to run weekly from launchd.

First run = BASELINE: records the current state and downloads nothing, so your
existing archive is not re-pulled. Every run after syncs only deltas (by
ModifiedClient timestamp per document ID).

Configuration (environment variables):
  RM_OUTPUT_DIR   where PDFs and notes go            (default ~/Documents/remarkable)
  RM_STATE_DIR    sync state and log                 (default ~/.local/state/remarkable)
  RM_FOLDER_MAP   JSON file mapping tablet folder -> output subfolder
                  (see folder_map.example.json; default: everything -> Unsorted)
  RM_EXCLUDE      colon-separated tablet folders to skip
                  (default /trash)
  RMAPI_PATH, RMC_PATH, RSVG_PATH   tool locations (default: found on PATH)

Usage:
  python3 remarkable_sync.py            sync deltas
  python3 remarkable_sync.py --reset    wipe state and re-baseline
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from remarkable_render import render_notebook, RMAPI  # noqa: E402

OUTPUT_DIR = Path(os.environ.get("RM_OUTPUT_DIR", "~/Documents/remarkable")).expanduser()
STATE_DIR = Path(os.environ.get("RM_STATE_DIR", "~/.local/state/remarkable")).expanduser()
STATE_FILE = STATE_DIR / "sync_state.json"
LOG_FILE = STATE_DIR / "sync.log"
EXCLUDE = [e for e in os.environ.get("RM_EXCLUDE", "/trash").split(":") if e]
UNSORTED = "Unsorted"


def load_folder_map() -> dict[str, str]:
    p = os.environ.get("RM_FOLDER_MAP")
    if not p:
        return {}
    return json.loads(Path(p).expanduser().read_text())


FOLDER_MAP = load_folder_map()


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
    print(line, file=sys.stderr)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def run(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.strip()).strip("-")
    return s or "untitled"


def list_files() -> list[str]:
    r = run([RMAPI, "find"])
    if r.returncode != 0:
        # Distinguish an rmapi auth/network failure from a genuinely empty cloud.
        log(f"rmapi find failed (exit {r.returncode}): {r.stderr.strip()[:300]}")
        return []
    out = []
    for ln in r.stdout.splitlines():
        if ln.startswith("[f] "):
            p = ln[4:]
            if not any(p == e or p.startswith(e + "/") for e in EXCLUDE):
                out.append(p)
    return out


def stat(path: str) -> dict | None:
    r = run([RMAPI, "stat", path])
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def route(path: str) -> dict:
    """Map a tablet path to {dest (relative to OUTPUT_DIR), stem}.

    FOLDER_MAP keys are tablet folder prefixes ("/Work/ProjectA"). The longest
    matching prefix wins. The stem is the path below the prefix, slugified.
    Unmapped paths go to Unsorted.
    """
    parts = [p for p in path.strip("/").split("/") if p]
    name = parts[-1] if parts else "untitled"
    best = ""
    for prefix in FOLDER_MAP:
        pp = prefix.rstrip("/")
        if (path == pp or path.startswith(pp + "/")) and len(pp) > len(best):
            best = pp
    if best:
        rest = [p for p in path[len(best):].split("/") if p]
        stem = "_".join(slug(p) for p in rest) or slug(name)
        return {"dest": FOLDER_MAP[best], "stem": stem}
    return {"dest": UNSORTED, "stem": "_".join(slug(p) for p in parts) or slug(name)}


def companion_md(path: str, r: dict, pdf_name: str, n_pages: int) -> str:
    today = datetime.now().date()
    return "\n".join([
        "---", f'title: "{r["stem"]}"', f"date: {today}", "source: remarkable",
        f'rm_path: "{path}"', "---", "",
        f"# {Path(path).name}", "",
        f"Handwritten reMarkable notebook ({n_pages} pages).", "",
        f"[{pdf_name}]({pdf_name})", "",
        f"Synced from `{path}` on {today}. PDF only (handwriting).", ""])


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    reset = "--reset" in sys.argv
    state = {} if reset else (json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {})
    docs = state.get("docs", {})
    baseline_done = state.get("baseline_done", False)

    log(f"start (baseline_done={baseline_done}, known={len(docs)})")
    paths = list_files()
    log(f"{len(paths)} watched files")

    current = {}
    for p in paths:
        s = stat(p)
        if s and s.get("Type") == "DocumentType" and s.get("ID"):
            current[s["ID"]] = {"modified": s.get("ModifiedClient", ""), "path": p}

    # First run: record state, download nothing.
    if not baseline_done:
        STATE_FILE.write_text(json.dumps({"baseline_done": True, "docs": current}, indent=2))
        log(f"BASELINE: recorded {len(current)} docs, downloaded 0. Future runs sync deltas.")
        return 0

    deltas = [(i, m) for i, m in current.items()
              if i not in docs or docs[i].get("modified") != m["modified"]]
    log(f"{len(deltas)} new/changed notebooks")

    synced = 0
    for doc_id, meta in deltas:
        path = meta["path"]
        r = route(path)
        dest_dir = OUTPUT_DIR / r["dest"]
        with tempfile.TemporaryDirectory() as td:
            pdf, n = render_notebook(path, Path(td), log=log)
            if not pdf:
                # not a notebook (uploaded pdf/epub), empty, or v5 format: remember so we don't retry weekly
                docs[doc_id] = meta
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            pdf_out = dest_dir / f"{r['stem']}.pdf"
            md_out = dest_dir / f"{r['stem']}.md"
            shutil.copy(pdf, pdf_out)
            md_out.write_text(companion_md(path, r, pdf_out.name, n))
            docs[doc_id] = meta
            synced += 1
            log(f"  ok {r['dest']}/{r['stem']}.pdf ({n} pp)")

    STATE_FILE.write_text(json.dumps({"baseline_done": True, "docs": docs}, indent=2))
    log(f"done: synced {synced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
