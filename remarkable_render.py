#!/usr/bin/env python3
"""
Shared reMarkable render pipeline (used by remarkable_sync.py and remarkable_import.py).

render_notebook(rm_path, work) downloads one notebook from the reMarkable cloud
and renders it to a multi-page PDF. PDF only, no OCR. Returns (pdf_path, n_pages),
or (None, 0) if it is not a handwritten notebook (for example an uploaded PDF or
epub) or rendering produced nothing.

Pipeline: rmapi geta -> unzip raw .rm -> rmc -t svg -> rsvg-convert -f pdf
-> merge pages (pypdf).

Tool locations: set RMAPI_PATH, RMC_PATH, RSVG_PATH, or leave them unset and the
tools are looked up on PATH.

Known limitation: notebooks saved in the old v5 .rm format do not render
(rmc only reads v6). They are skipped.
"""
from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path


def find_tool(env_var: str, name: str) -> Path:
    p = os.environ.get(env_var) or shutil.which(name)
    if not p:
        raise SystemExit(f"{name} not found. Install it or set {env_var}.")
    return Path(p)


RMAPI = find_tool("RMAPI_PATH", "rmapi")
RMC = find_tool("RMC_PATH", "rmc")
RSVG = find_tool("RSVG_PATH", "rsvg-convert")


def _run(cmd, cwd=None):
    return subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)


def _page_order(content_path: Path) -> list[str]:
    d = json.loads(content_path.read_text())
    pages = (d.get("cPages") or {}).get("pages")
    if pages:
        live = [p for p in pages if "deleted" not in p]
        live.sort(key=lambda p: (p.get("idx") or {}).get("value", ""))
        return [p["id"] for p in live]
    return d.get("pages") or []


def render_notebook(rm_path: str, work: Path, log=print) -> tuple[Path | None, int]:
    """Return (pdf_path or None, n_pages). None if not a notebook / no pages."""
    _run([RMAPI, "geta", rm_path], cwd=work)
    zips = list(work.glob("*.zip"))
    if not zips:
        log(f"  ! no download for {rm_path}")
        return None, 0
    ex = work / "x"
    ex.mkdir(exist_ok=True)
    _run(["unzip", "-o", str(zips[0]), "-d", str(ex)])
    content = next(ex.glob("*.content"), None)
    if not content:
        return None, 0
    # skip uploaded PDFs / epubs: only render native handwritten notebooks
    try:
        ftype = json.loads(content.read_text()).get("fileType", "")
    except Exception:
        ftype = ""
    if ftype not in ("", "notebook"):
        log(f"  - skip {rm_path} (fileType={ftype}, not handwriting)")
        return None, 0

    doc_id = content.stem
    order = _page_order(content)
    if not order:
        return None, 0

    page_pdfs = []
    for i, pid in enumerate(order, 1):
        rmf = ex / doc_id / f"{pid}.rm"
        if not rmf.exists():
            continue
        svg, pdf = work / f"p{i:03d}.svg", work / f"p{i:03d}.pdf"
        if _run([RMC, "-t", "svg", rmf, "-o", svg]).returncode != 0 or not svg.exists() or svg.stat().st_size == 0:
            continue
        if _run([RSVG, "-f", "pdf", "-o", pdf, svg]).returncode != 0 or not pdf.exists():
            continue
        page_pdfs.append(pdf)

    if not page_pdfs:
        return None, 0

    import pypdf
    out = work / "merged.pdf"
    w = pypdf.PdfWriter()
    for p in page_pdfs:
        w.append(str(p))
    with out.open("wb") as fh:
        w.write(fh)
    return out, len(page_pdfs)
