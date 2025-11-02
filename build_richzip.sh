#!/usr/bin/env bash
set -euo pipefail

# === CONFIG ===
SRC_DIR="richdatabundle_site_v2"    # change to your local extracted folder name if different
OUT_ZIP="richdatabundle_fixed.zip"
TOP_DIR_IN_ZIP="richdatabundle_fixed"
PROJECT_FOLDER_NAME="richdatabundle_project"   # folder name that contains settings.py in your project
MAP_PROJECT_TO="backend"
MAX_SIZE_BYTES=$((20 * 1024 * 1024))   # skip files >20MB
# ==============

if [ ! -d "$SRC_DIR" ]; then
  echo "Source dir '$SRC_DIR' not found. Run this script from the parent folder of your project."
  exit 1
fi

# Remove old zip
rm -f "$OUT_ZIP"

# Prepare file list and filter
# We'll create the zip by walking files and adding only what we want.
python3 - "$SRC_DIR" "$OUT_ZIP" "$TOP_DIR_IN_ZIP" "$PROJECT_FOLDER_NAME" "$MAP_PROJECT_TO" "$MAX_SIZE_BYTES" <<'PY'
import os, sys, zipfile, pathlib

SRC = sys.argv[1]
OUT_ZIP = sys.argv[2]
TOP = sys.argv[3]
PROJECT_NAME = sys.argv[4]
MAP_TO = sys.argv[5]
MAX_SIZE = int(sys.argv[6])

exclude_dirs = {'.git','venv','__pycache__','.pytest_cache','node_modules','.cache','.hg','.idea'}
exclude_name_parts = {'images','image','media'}
exclude_filenames = {'.env'}

def should_exclude(rel):
    # lower parts check
    parts = [p.lower() for p in pathlib.Path(rel).parts]
    if os.path.basename(rel) in exclude_filenames:
        return True, "forbidden_filename"
    for p in parts:
        if p in exclude_dirs:
            return True, "excluded_dir"
        if p in exclude_name_parts:
            return True, "image_or_media"
    # exclude static/js prefix
    if rel.startswith("static/js") or "/static/js/" in rel or rel.startswith("core/static/js") or "/core/static/js/" in rel:
        return True, "static_js"
    return False, None

with zipfile.ZipFile(OUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:
    included = 0
    skipped = 0
    for root, dirs, files in os.walk(SRC):
        # prune
        dirs[:] = [d for d in dirs if d not in exclude_dirs and d.lower() not in exclude_name_parts]
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, SRC).replace("\\", "/")
            ex, reason = should_exclude(rel_path)
            if ex:
                skipped += 1
                continue
            try:
                size = os.path.getsize(abs_path)
                if size > MAX_SIZE:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue
            # remap project folder name to MAP_TO inside zip if needed
            parts = rel_path.split('/')
            if parts[0] == PROJECT_NAME:
                parts[0] = MAP_TO
            arcname = TOP + "/" + "/".join(parts)
            try:
                zf.write(abs_path, arcname)
                included += 1
            except Exception:
                skipped += 1
                continue
    print(f"ZIP_CREATED included={included} skipped={skipped}")
PY

echo "Done. Created $OUT_ZIP"
