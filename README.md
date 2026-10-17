# remarkable-toolchain

Render handwritten reMarkable notebooks to PDF and file them into a folder on your Mac. Includes a weekly delta sync and a one-time curated import.

## What it does

- `remarkable_render.py`: downloads one notebook with rmapi, renders each page (`rmc` to SVG, `rsvg-convert` to PDF) and merges the pages with pypdf.
- `remarkable_sync.py`: finds notebooks that are new or edited since the last run and writes each as `<stem>.pdf` plus a small `<stem>.md` note under `OUTPUT_DIR`. The first run records a baseline and downloads nothing.
- `remarkable_import.py`: renders a list of notebooks from a JSON manifest. Use it once to build an initial archive.

PDF only. There is no OCR.

## Requirements

- Python 3.10 or newer
- [rmapi](https://github.com/ddvk/rmapi), logged in to your reMarkable cloud account (run `rmapi` once to authenticate)
- [rmc](https://github.com/ricklupton/rmc) (`pip install rmc`)
- `rsvg-convert` (`brew install librsvg`)
- [pypdf](https://pypi.org/project/pypdf/) (`pip install pypdf`)
- `unzip` (ships with macOS)

## Install

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    brew install librsvg
    # install rmapi and log in

## Configure

All settings are environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `RM_OUTPUT_DIR` | `~/Documents/remarkable` | Where PDFs and notes are written |
| `RM_STATE_DIR` | `~/.local/state/remarkable` | Sync state and log |
| `RM_FOLDER_MAP` | none | JSON file mapping tablet folders to output subfolders |
| `RM_EXCLUDE` | `/trash` | Colon-separated tablet folders to skip, for example `/Reading:/trash` |
| `RMAPI_PATH`, `RMC_PATH`, `RSVG_PATH` | found on `PATH` | Tool locations |

Folder map example (`folder_map.example.json`):

    {"/Work": "Work", "/Personal": "Personal", "/School/Term1": "School/Term1"}

The longest matching prefix wins. A notebook at `/Work/Notes/Weekly` goes to `OUTPUT_DIR/Work/Notes_Weekly.pdf`. Anything unmapped goes to `OUTPUT_DIR/Unsorted`.

## Usage

    export RM_OUTPUT_DIR=~/Documents/remarkable
    export RM_FOLDER_MAP=folder_map.json
    .venv/bin/python3 remarkable_sync.py           # first run: baseline only
    .venv/bin/python3 remarkable_sync.py           # later runs: deltas
    .venv/bin/python3 remarkable_sync.py --reset   # forget state, re-baseline
    .venv/bin/python3 remarkable_import.py manifest.json

## Weekly sync with launchd

Edit the paths in `launchd/com.example.remarkable-sync.plist`, then:

    cp launchd/com.example.remarkable-sync.plist ~/Library/LaunchAgents/
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.remarkable-sync.plist

It runs Sundays at 10:00. Use an absolute path to the venv python so launchd finds pypdf and rmc. Put the tools' folder (for example `/opt/homebrew/bin`) in the plist `PATH`, or set the `*_PATH` variables.

## Limitations

- Notebooks saved in the old v5 `.rm` format do not render. `rmc` reads v6 only. They are skipped and marked as seen, so they are not retried.
- Uploaded PDFs and epubs are skipped. Only native handwritten notebooks render.
- Downloads go through the reMarkable cloud and can be slow for large notebooks.
- No OCR. Use the tablet's on-device "Convert to text" if you need text.
- macOS paths and launchd are assumed in the examples. The Python itself is portable.

## License

MIT
