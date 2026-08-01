# Card sheet splitter

`extract_cards.py` cuts the individual cards out of a print-and-play PDF whose
pages hold a grid of cards, and writes each one as its own PNG.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Cutting this deck

`./extract_all.sh` splits the bundled PDF into the four expansions, grouped by
the icon at the bottom centre of each card, and writes the shared back:

| folder | pages | icon | cards |
| --- | --- | --- | --- |
| `out/base` | 1, 3, 5, 7, 9, 11 | none | 95 |
| `out/dunwich` | 13, 15 | black barn | 31 |
| `out/innsmouth` | 17, 19 | white anchor | 27 |
| `out/kingsport` | 21, 23, 25 | lighthouse beam | 39 |
| `out/back.png` | 2 | — | 1 |

That is 192 cards, every one 411x677. Blank filler slots are skipped: one at the
end of page 11, one on page 15, five on page 19 and nine on page 25.

## Usage

Start by looking at what is on each sheet:

```bash
.venv/bin/python extract_cards.py AlternateClues-Printable-Exps-v1.1.pdf --list
```

```
 page     grid  slots  cards  blanks
    1  4x4         16     16  -
   11  4x4         16     15  16
   19  4x4         16     11  12,13,14,15,16
   25  4x4         16      7  8,9,10,11,12,13,14,15,16
```

Then cut a group of pages into one folder:

```bash
.venv/bin/python extract_cards.py AlternateClues-Printable-Exps-v1.1.pdf \
    --pages 1,3,5 --count 16 --out out/dunwich
```

Cards are numbered in reading order, left to right and then top to bottom, so
`--count 9` on a 4-column sheet takes the first two rows plus the first card of
the third row.

### Selecting pages

`--pages` takes `odd` (the default), `even`, `all`, single pages, ranges, and
stepped ranges, in any comma-separated combination: `--pages 1,3,7-13,17-25/2`.

### Selecting how many cards

`--count` accepts:

| value | meaning |
| --- | --- |
| `auto` (default) | take every card, stopping at the trailing blank slots |
| `11` | take the first 11 cards on every selected page |
| `16,16,11` | one count per selected page, in order |
| `19:11,25:7` | counts for specific pages; the rest fall back to `auto` |

### Other options

- `--out` — destination folder, created if missing. Existing files are kept
  unless you pass `--force`.
- `--name seq` (default) names files `card_001.png` and keeps counting across
  pages; `--name page` names them `card_p19_c03.png` instead. `--prefix`
  changes the `card` part.
- `--dry-run` reports what would be written without writing it.
- `--manifest` also writes a `manifest.csv` recording the page, row and column
  each PNG came from.
- `--no-trim` keeps the gutter padding around each card instead of cropping
  tight to the art.
- `--ref-page N` crops every card to the card rectangle measured on page `N`
  rather than to its own art. Card backs are printed with bleed, so trimming one
  on its own gives a 448x724 image where a front gives 411x677;
  `--pages 2 --ref-page 1` cuts the back to the front's size instead.

## How it works

Each card on these sheets is a separate embedded image, so the script pulls
those out at their native resolution rather than rasterising and slicing the
page. The paper margin never enters the picture, and no resampling happens.
It then crops the gutter padding around each card, requiring that a good share
of an edge line differ from the padding colour so that the thin cut marks
printed in the gutter do not hold the crop open.

Empty slots are detected by how little dark pixel coverage the card body has:
the filler cards carry the deck frame but no text. On the bundled PDF the
blanks score under 0.011 and real cards over 0.034, so the 0.02 cutoff has
wide margins on both sides.

For a sheet built from vector art instead of embedded images, `--mode render`
rasterises the page at `--dpi`, trims the paper margin and slices the remainder
into a `--rows` by `--cols` grid. On this PDF both paths agree to within a
pixel or two.
