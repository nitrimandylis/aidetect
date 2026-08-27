#!/bin/bash
# Download the IBO "50 Excellent Extended Essays" exemplars from the Wayback
# Machine. These are the human half of the calibration set.
#
#   ./fetch_exemplars.sh scans
#
# Every PDF carries "(c) International Baccalaureate Organization 2008" on each
# page and a 2008 CreationDate, and every capture predates 2020, which is what
# makes the human class provably human. See corpora/README.md for the licence
# position: this material is not covered by the repo's MIT licence.
#
# The `id_` in the URL asks Wayback for the original bytes rather than its
# rewritten HTML wrapper. Two of the 48 (Economics_1, English_7) have no usable
# capture; the script reports them and carries on.
#
# Safe to re-run: an essay already downloaded is skipped.
set -u
outdir="${1:?usage: fetch_exemplars.sh <output-folder>}"
mkdir -p "$outdir"

NAMES="Biology_1 Biology_2 Biology_3 Chemistry_1 Chemistry_2 Chemistry_3
Economics_1 English_1 English_2 English_3 English_5 English_6 English_7
English_8 Geography_1 Geography_2 Geography_3 History_1 History_2 History_4
History_5 ITGS_1 ITGS_2 Mathmatics_1 Mathmatics_2 Mathmatics_3 Mathmatics_4
Music_1 Philosophy_1 Philosophy_2 Philosophy_3 Philosophy_4 Physics_1 Physics_2
Politics_1 Politics_2 Politics_3 Psychology_1 Psychology_2 Psychology_3
Social_and_cultural_anthropology_1 Social_and_cultural_anthropology_2
Visual_Arts_1 Visual_Arts_2 Visual_Arts_3 Visual_Arts_4 World_Religion_1
World_Religion_2"

fetch_one() {
  name="$1"; outdir="$2"
  out="$outdir/$name.pdf"
  if [ -s "$out" ] && [ "$(stat -f%z "$out")" -gt 100000 ]; then
    echo "have $name"; return 0
  fi
  for attempt in 1 2 3; do
    curl -sL --max-time 300 --retry 2 \
      "https://web.archive.org/web/2018id_/https://www.easthartford.org/uploaded/ciba/$name.pdf" \
      -o "$out"
    size=$(stat -f%z "$out" 2>/dev/null || echo 0)
    if [ "$size" -gt 100000 ] && head -c 5 "$out" | grep -q '%PDF'; then
      echo "ok $name ($size bytes)"; return 0
    fi
    sleep $((attempt * 5))
  done
  echo "NO CAPTURE $name"; rm -f "$out"; return 1
}
export -f fetch_one

# Four at a time: Wayback throttles harder than that.
echo "$NAMES" | tr ' \n' '\n\n' | grep -v '^$' \
  | xargs -P 4 -I{} bash -c 'fetch_one "$@"' _ {} "$outdir"

echo
echo "downloaded $(ls "$outdir"/*.pdf 2>/dev/null | wc -l | tr -d ' ') of 48 exemplars into $outdir"
