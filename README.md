# Alternate Clues Variant

A phone-sized card reader for the **Alternate Clues** variant of *Arkham Horror*
(2nd edition). Pick your expansions, shuffle, and draw — so nobody has to print
192 cards.

**→ [Play it](https://gustavomicha.github.io/ah-clues-variant-app/)**

## The variant

Whenever you draw a Mythos card during the Mythos Phase, look at its *Clue
Appears At:* entry. For each Clue that card would place, draw one Alternate
Clues card instead and follow the instructions on it. The full rules are in the
app under **Rules**, and in the [original BGG thread][thread].

The variant, and every card in it, is the work of **Ville-Veikko Jylhämäki**
([@Cancelion][thread]). The expansion symbols on the cards were added by
**Eduardo Hellas** (@ehellas). This repository only wraps their work in a
browser.

[thread]: https://boardgamegeek.com/thread/1835036/alternate-clues-variant-stable-locations-here-we-c

## Using it

Base game cards are always in the deck; Dunwich, Innsmouth and Kingsport are
opt-in. Draw with the button, a tap on the card, or a swipe; **Back** walks the
cards you have already read.

Your deck, position and expansion choices survive a reload, so a locked phone
mid-game costs nothing. You always land on the menu, which offers to **Resume**
where you left off rather than dropping you back into the deck unasked.

On iOS or Android, *Add to Home Screen* gives it a launcher icon and drops the
browser chrome.

| deck | cards |
| --- | --- |
| Base game | 95 |
| The Dunwich Horror | 31 |
| Innsmouth Horror | 27 |
| Kingsport Horror | 39 |
| **all four** | **192** |

## Layout

```
index.html            the whole app: setup, game, rules and credits screens
assets/css/style.css
assets/js/app.js      deck, cursor and persistence
cards/                192 WebP fronts + the shared back, what the app serves
cards/manifest.json   generated: which cards belong to which expansion
source/               the lossless PNGs the WebPs are built from
tools/build_cards.py  source/*.png -> cards/*.webp + manifest
extractor/            how the PNGs were cut out of the print-and-play PDF
```

Nothing is built, bundled or installed to run this — it is three static files
and a folder of images. Serve the directory and open it:

```bash
python3 -m http.server 8000
```

### Regenerating the cards

Only needed if `source/` changes. The WebP set is ~10 MB against the PNGs' 85 MB,
which is the difference between a card arriving instantly on phone data and not.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tools/build_cards.py --force
```

`extractor/` holds the script that cut the individual cards out of the
print-and-play PDF in the first place; see its README. The PDF itself is not in
this repository.

## Credits and rights

*Arkham Horror* is a trademark of Fantasy Flight Games. The card artwork belongs
to its respective owners and is reproduced here by fans, for fans, with credit
to the people named above.
