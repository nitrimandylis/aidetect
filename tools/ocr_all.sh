#!/bin/bash
# OCR every downloaded scan, waiting for the downloader to finish first.
cd "$(dirname "$0")"
scans=~/cc/aidetect-scans
for i in $(seq 1 60); do
  n=$(ls "$scans"/*.pdf 2>/dev/null | wc -l | tr -d ' ')
  pgrep -f "fetch.sh" >/dev/null || { echo "downloader done at $n pdfs"; break; }
  echo "waiting: $n pdfs so far"; sleep 20
done
ls "$scans"/*.pdf | xargs -P 4 -I{} ./run_ocr.sh {} "$scans/tsv"
echo "OCR COMPLETE: $(ls "$scans"/tsv/*.tsv | wc -l | tr -d ' ') essays"
