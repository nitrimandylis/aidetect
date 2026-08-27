#!/bin/bash
# Render a scanned EE to 200 dpi grayscale pages and OCR them to one TSV.
#   ./run_ocr.sh ~/cc/aidetect-scans/English_1.pdf ~/cc/aidetect-scans/tsv
set -e
pdf="$1"; outdir="$2"
name=$(basename "$pdf" .pdf)
[ -s "$outdir/$name.tsv" ] && { echo "have $name"; exit 0; }
mkdir -p "$outdir"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
pdftoppm -r 200 -gray -png "$pdf" "$tmp/pg"
"$(dirname "$0")/ocr" "$tmp"/pg-*.png > "$outdir/$name.tsv"
echo "ocr $name  $(ls "$tmp"/pg-*.png | wc -l | tr -d ' ') pages"
