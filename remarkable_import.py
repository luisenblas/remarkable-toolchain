#!/usr/bin/env python3
"""
reMarkable curated importer (one-time).

Pulls a list of native reMarkable notebooks, renders each to a PDF, and writes it
under OUTPUT_DIR with a small companion .md note. Handwriting is kept as PDF (no OCR).
Notebooks whose PDF already exists are skipped.

The list comes from a JSON manifest (see manifest.example.json):
  [{"rm": "/Work/Notes/Meeting", "dest": "Work", "stem": "Work_Meeting"}, ...]
    rm    path on the tablet (as shown by `rmapi find`)
    dest  subfolder of OUTPUT_DIR
    stem  output file name without extension

Usage:  python3 remarkable_import.py manifest.json
Env:    RM_OUTPUT_DIR (default ~/Documents/remarkable), RMAPI_PATH, RMC_PATH, RSVG_PATH
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from remarkable_render import render_notebook  # noqa: E402

OUTPUT_DIR = Path(os.environ.get("RM_OUTPUT_DIR", "~/Documents/remarkable")).expanduser()


def companion_md(item: dict, pdf_name: str, n_pages: int) -> str:
    return "\n".join([
        "---", f'title: "{item["stem"]}"', f"date: {date.today()}", "source: remarkable",
        f'rm_path: "{item["rm"]}"', "---", "",
        f"# {Path(item['rm']).name}", "",
        f"Handwritten reMarkable notebook ({n_pages} pages).", "",
        f"[{pdf_name}]({pdf_name})", "",
        f"Imported from `{item['rm']}` on {date.today()}. PDF only (handwriting). "
        f"For text, use the tablet's on-device Convert to text.", ""])


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    manifest = json.loads(Path(sys.argv[1]).expanduser().read_text())

    ok, fail = 0, 0
    for item in manifest:
        print(f"\n[{item['stem']}]  <-  {item['rm']}")
        dest_dir = OUTPUT_DIR / item["dest"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        pdf_out = dest_dir / f"{item['stem']}.pdf"
        md_out = dest_dir / f"{item['stem']}.md"
        if pdf_out.exists():
            print("  already imported, skipping")
            continue

        with tempfile.TemporaryDirectory() as td:
            merged, n_pages = render_notebook(item["rm"], Path(td))
            if not merged:
                fail += 1
                continue
            shutil.copy(merged, pdf_out)
            md_out.write_text(companion_md(item, pdf_out.name, n_pages))
            print(f"  ok {pdf_out}  ({pdf_out.stat().st_size / 1e6:.1f} MB, {n_pages} pp)")
            ok += 1

    print(f"\nDone: {ok} imported, {fail} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
