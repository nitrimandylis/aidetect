#!/bin/bash
# OCR every PDF in a folder, four at a time.
#
#   ./ocr_all.sh scans           # writes scans/tsv/<essay>.tsv
#
# Safe to re-run: run_ocr.sh skips an essay that already has a TSV.
set -e
scans="${1:?usage: ocr_all.sh <folder-of-pdfs>}"
here="$(cd "$(dirname "$0")" && pwd)"
ls "$scans"/*.pdf | xargs -P 4 -I{} "$here/run_ocr.sh" {} "$scans/tsv"
echo "OCR complete: $(ls "$scans"/tsv/*.tsv | wc -l | tr -d ' ') essays"
