#!/usr/bin/env python3
"""Turn the extracted card PNGs into the WebP set the webapp serves.

The PNGs under `source/` are the master copies: lossless, ~425 KB each, 85 MB
all told. That is far too much to push down a phone connection one card at a
time, so this writes a parallel `cards/` tree of WebP images at roughly a tenth
the weight, plus the manifest the app reads to build its decks.

    .venv/bin/python tools/build_cards.py

Existing files are left alone unless you pass --force.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source"
DEST = ROOT / "cards"

# Quality 88 keeps the card text crisp at 411x677 while landing around 47 KB,
# down from the 425 KB the lossless PNG costs.
QUALITY = 88
METHOD = 6

# Every card front is 411x677; the shared back was extracted with print bleed
# and comes out taller and wider, so it gets cropped to the front's aspect
# before scaling. The crop only eats into the black border.
CARD_W, CARD_H = 411, 677
CARD_ASPECT = CARD_W / CARD_H

EXPANSIONS = [
    {"id": "base", "name": "Arkham Horror", "short": "Base game", "always": True},
    {"id": "dunwich", "name": "The Dunwich Horror", "short": "Dunwich", "always": False},
    {"id": "innsmouth", "name": "Innsmouth Horror", "short": "Innsmouth", "always": False},
    {"id": "kingsport", "name": "Kingsport Horror", "short": "Kingsport", "always": False},
]


def to_webp(src: Path, dst: Path, force: bool = False) -> bool:
    """Write `src` as WebP at `dst`. Returns True if it actually wrote."""
    if dst.exists() and not force:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.convert("RGB").save(dst, "WEBP", quality=QUALITY, method=METHOD)
    return True


def build_back(force: bool = False) -> None:
    """Crop the bleed off the shared back and match it to the card size."""
    dst = DEST / "back.webp"
    if dst.exists() and not force:
        return
    with Image.open(SOURCE / "back.png") as im:
        w, h = im.size
        target_w = round(h * CARD_ASPECT)
        if target_w <= w:
            off = (w - target_w) // 2
            box = (off, 0, off + target_w, h)
        else:
            target_h = round(w / CARD_ASPECT)
            off = (h - target_h) // 2
            box = (0, off, w, off + target_h)
        im = im.crop(box).resize((CARD_W, CARD_H), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.convert("RGB").save(dst, "WEBP", quality=QUALITY, method=METHOD)


def build_logo(force: bool = False) -> None:
    """The logo keeps its alpha channel, so it stays a lossless WebP."""
    dst = DEST.parent / "assets" / "img" / "logo.webp"
    if dst.exists() and not force:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE / "ahb01_logo.png") as im:
        im.convert("RGBA").save(dst, "WEBP", lossless=True, method=METHOD)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--clean", action="store_true", help="delete cards/ first")
    args = ap.parse_args()

    if args.clean and DEST.exists():
        shutil.rmtree(DEST)

    manifest = {
        "generated_from": "source/",
        "card_size": [CARD_W, CARD_H],
        "back": "cards/back.webp",
        "expansions": [],
    }

    written = 0
    for exp in EXPANSIONS:
        folder = SOURCE / exp["id"]
        pngs = sorted(folder.glob("*.png"))
        if not pngs:
            raise SystemExit(f"no PNGs in {folder}")

        cards = []
        for png in pngs:
            out = DEST / exp["id"] / f"{png.stem}.webp"
            written += to_webp(png, out, args.force)
            cards.append(png.stem)

        manifest["expansions"].append(
            {
                "id": exp["id"],
                "name": exp["name"],
                "short": exp["short"],
                "always": exp["always"],
                "dir": f"cards/{exp['id']}",
                "count": len(cards),
                "cards": cards,
            }
        )
        print(f"{exp['id']:<10} {len(cards):>3} cards")

    build_back(args.force)
    build_logo(args.force)

    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    total = sum(e["count"] for e in manifest["expansions"])
    size = sum(p.stat().st_size for p in DEST.rglob("*.webp")) / 1e6
    print(f"\n{total} cards, {written} newly converted, {size:.1f} MB in cards/")


if __name__ == "__main__":
    main()
