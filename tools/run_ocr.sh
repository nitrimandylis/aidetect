#!/bin/bash
# Render one scanned Extended Essay to 200 dpi grayscale pages and OCR them
# into a single TSV.
#
#   ./run_ocr.sh scans/English_1.pdf scans/tsv
#
# Compiles ocr.swift on first use, so the binary never has to be committed.
set -e
pdf="$1"; outdir="$2"
if [ -z "$pdf" ] || [ -z "$outdir" ]; then
  echo "usage: run_ocr.sh <essay.pdf> <tsv-output-dir>" >&2; exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
if [ ! -x "$here/ocr" ] || [ "$here/ocr.swift" -nt "$here/ocr" ]; then
  echo "compiling ocr.swift..." >&2
  swiftc -O "$here/ocr.swift" -o "$here/ocr"
fi

name=$(basename "$pdf" .pdf)
[ -s "$outdir/$name.tsv" ] && { echo "have $name"; exit 0; }
mkdir -p "$outdir"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
pdftoppm -r 200 -gray -png "$pdf" "$tmp/pg"
"$here/ocr" "$tmp"/pg-*.png > "$outdir/$name.tsv"
echo "ocr $name  $(ls "$tmp"/pg-*.png | wc -l | tr -d ' ') pages"
