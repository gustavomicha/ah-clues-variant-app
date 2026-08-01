#!/usr/bin/env bash
# Cut every non-blank card into its expansion folder, grouped by the icon at the
# bottom centre of the card, plus the shared card back.
set -euo pipefail

cd "$(dirname "$0")"

PDF="${1:-AlternateClues-Printable-Exps-v1.1.pdf}"
PY=".venv/bin/python"
OUT="out"

rm -rf "$OUT"

# base has no icon, dunwich a barn, innsmouth an anchor, kingsport a lighthouse.
for spec in "1,3,5,7,9,11:base" "13,15:dunwich" "17,19:innsmouth" "21,23,25:kingsport"; do
    pages="${spec%%:*}"
    name="${spec##*:}"
    "$PY" extract_cards.py "$PDF" \
        --pages "$pages" --count auto \
        --out "$OUT/$name" --prefix "$name" --manifest
done

# The back is printed with bleed, so borrow the card rectangle from a page of
# fronts to keep it the same size as every card.
"$PY" extract_cards.py "$PDF" \
    --pages 2 --count 1 --out "$OUT" --prefix back --ref-page 1 --force
mv "$OUT/back_001.png" "$OUT/back.png"

echo
echo "$(find "$OUT" -name '*.png' | wc -l | tr -d ' ') PNGs in $OUT/"
