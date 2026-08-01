#!/usr/bin/env python3
"""Cut individual card images out of a print-and-play card-sheet PDF.

Cards are read in reading order (left to right, then top to bottom), so a count
of 9 on a 4-column sheet means the first two full rows plus the first card of
the third row.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from dataclasses import dataclass
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

# Blank filler cards keep the deck frame but have no text in the body, so the
# fraction of dark pixels there separates them from real cards by a wide margin.
BLANK_INK_THRESHOLD = 0.02
BORDER_TOLERANCE = 18
EDGE_COVERAGE = 0.5


@dataclass
class Slot:
    """One grid position on a sheet, with the card art found there."""

    page: int
    row: int
    col: int
    index: int
    image: Image.Image
    ink: float

    @property
    def is_blank(self) -> bool:
        return self.ink < BLANK_INK_THRESHOLD


def parse_pages(spec: str, page_count: int) -> list[int]:
    """Turn a page spec into a sorted list of 1-based page numbers.

    Accepts ``odd``, ``even``, ``all``, single pages, ``5-9`` ranges and
    ``1-25/2`` stepped ranges, combined with commas.
    """
    spec = spec.strip().lower()
    if spec == "odd":
        return list(range(1, page_count + 1, 2))
    if spec == "even":
        return list(range(2, page_count + 1, 2))
    if spec == "all":
        return list(range(1, page_count + 1))

    pages: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        step = 1
        if "/" in token:
            token, _, step_text = token.partition("/")
            step = int(step_text)
            if step < 1:
                raise ValueError(f"step must be positive in {token!r}")
        if "-" in token:
            start_text, _, end_text = token.partition("-")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"range {token!r} runs backwards")
            pages.update(range(start, end + 1, step))
        else:
            pages.add(int(token))

    bad = [p for p in pages if not 1 <= p <= page_count]
    if bad:
        raise ValueError(f"pages out of range 1..{page_count}: {sorted(bad)}")
    return sorted(pages)


def parse_counts(spec: str, pages: list[int]) -> dict[int, int | None]:
    """Map each page to how many cards to take, where ``None`` means auto-detect."""
    spec = spec.strip().lower()
    if spec == "auto":
        return {p: None for p in pages}

    tokens = [t.strip() for t in spec.split(",") if t.strip()]
    keyed = [t for t in tokens if ":" in t]
    if keyed and len(keyed) != len(tokens):
        raise ValueError("mix of 'page:count' and plain counts in --count")

    if keyed:
        counts: dict[int, int | None] = {p: None for p in pages}
        for token in keyed:
            page_text, _, count_text = token.partition(":")
            page = int(page_text)
            if page not in pages:
                raise ValueError(f"--count refers to page {page}, which is not selected")
            counts[page] = int(count_text)
        return counts

    if len(tokens) == 1:
        return {p: int(tokens[0]) for p in pages}
    if len(tokens) != len(pages):
        raise ValueError(
            f"--count has {len(tokens)} values but {len(pages)} pages are selected; "
            "pass one value, one per page, or 'page:count' pairs"
        )
    return {p: int(t) for p, t in zip(pages, tokens)}


def art_box(
    image: Image.Image,
    tolerance: int = BORDER_TOLERANCE,
    coverage: float = EDGE_COVERAGE,
) -> tuple[int, int, int, int]:
    """Locate the card art inside its uniform padding (black gutter or white paper).

    An edge only counts once a good share of the line differs from the padding
    colour, so thin registration and cut marks printed in the gutter are ignored.
    """
    pixels = np.asarray(image.convert("RGB")).astype(np.int16)
    edges = np.concatenate(
        [pixels[0, :, :], pixels[-1, :, :], pixels[:, 0, :], pixels[:, -1, :]]
    )
    background = np.median(edges, axis=0)
    mask = np.abs(pixels - background).max(axis=2) > tolerance
    if not mask.any():
        return (0, 0, image.width, image.height)

    rows = np.where(mask.mean(axis=1) >= coverage)[0]
    cols = np.where(mask.mean(axis=0) >= coverage)[0]
    if not rows.size or not cols.size:
        rows, cols = np.where(mask)
    return (int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1)


def trim_border(image: Image.Image) -> Image.Image:
    """Crop away the uniform padding around the card art."""
    return image.crop(art_box(image))


def crop_to_window(
    image: Image.Image, window: tuple[float, float, float, float]
) -> Image.Image:
    """Crop to a card rectangle given as fractions of the image size."""
    left, top, right, bottom = window
    return image.crop(
        (
            round(left * image.width),
            round(top * image.height),
            round(right * image.width),
            round(bottom * image.height),
        )
    )


def ink_fraction(image: Image.Image) -> float:
    """Fraction of dark pixels in the card body, ignoring frame and title band."""
    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    body = gray[
        int(height * 0.245) : int(height * 0.905),
        int(width * 0.14) : int(width * 0.86),
    ]
    if body.size == 0:
        return 1.0
    return float((body < 110).mean())


def _pil_from_xref(doc: fitz.Document, xref: int) -> Image.Image:
    info = doc.extract_image(xref)
    image = Image.open(io.BytesIO(info["image"]))
    smask = info.get("smask")
    if smask:
        alpha = Image.open(io.BytesIO(doc.extract_image(smask)["image"])).convert("L")
        image = image.convert("RGBA")
        image.putalpha(alpha.resize(image.size))
        return image
    return image.convert("RGB")


def _group_rows(items: list[tuple[fitz.Rect, int]]) -> list[list[tuple[fitz.Rect, int]]]:
    """Cluster placements into rows by vertical position, then order each row."""
    items = sorted(items, key=lambda item: item[0].y0)
    heights = [rect.height for rect, _ in items]
    tolerance = float(np.median(heights)) * 0.4
    rows: list[list[tuple[fitz.Rect, int]]] = []
    for rect, xref in items:
        if rows and abs(rect.y0 - rows[-1][0][0].y0) <= tolerance:
            rows[-1].append((rect, xref))
        else:
            rows.append([(rect, xref)])
    return [sorted(row, key=lambda item: item[0].x0) for row in rows]


def slots_from_images(doc: fitz.Document, page_number: int) -> list[Slot]:
    """Pull the embedded card images off a sheet at their native resolution."""
    page = doc[page_number - 1]
    placements = [
        (fitz.Rect(info["bbox"]), info["xref"])
        for info in page.get_image_info(xrefs=True)
    ]
    if not placements:
        return []

    slots: list[Slot] = []
    for row_index, row in enumerate(_group_rows(placements), start=1):
        for col_index, (_, xref) in enumerate(row, start=1):
            image = _pil_from_xref(doc, xref)
            slots.append(
                Slot(
                    page=page_number,
                    row=row_index,
                    col=col_index,
                    index=len(slots) + 1,
                    image=image,
                    ink=ink_fraction(image),
                )
            )
    return slots


def slots_from_render(
    doc: fitz.Document, page_number: int, rows: int, cols: int, dpi: int
) -> list[Slot]:
    """Fallback for vector sheets: rasterise, drop the paper margin, slice the grid."""
    pixmap = doc[page_number - 1].get_pixmap(dpi=dpi)
    page_image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
    sheet = trim_border(page_image)
    cell_width = sheet.width / cols
    cell_height = sheet.height / rows

    slots: list[Slot] = []
    for row_index in range(rows):
        for col_index in range(cols):
            cell = sheet.crop(
                (
                    round(col_index * cell_width),
                    round(row_index * cell_height),
                    round((col_index + 1) * cell_width),
                    round((row_index + 1) * cell_height),
                )
            )
            slots.append(
                Slot(
                    page=page_number,
                    row=row_index + 1,
                    col=col_index + 1,
                    index=len(slots) + 1,
                    image=cell,
                    ink=ink_fraction(cell),
                )
            )
    return slots


def load_slots(doc: fitz.Document, page_number: int, args) -> list[Slot]:
    if args.mode != "render":
        slots = slots_from_images(doc, page_number)
        if slots:
            return slots
        if args.mode == "extract":
            raise RuntimeError(
                f"page {page_number} has no embedded images; try --mode render"
            )
    return slots_from_render(doc, page_number, args.rows, args.cols, args.dpi)


def measure_window(
    doc: fitz.Document, page_number: int, args
) -> tuple[float, float, float, float]:
    """Measure the card rectangle on a reference page, as fractions of image size.

    Card backs are printed with bleed, so trimming one to its own art gives a
    bigger picture than a front. Borrowing the window from a page of fronts
    keeps every PNG the same size.
    """
    boxes = []
    for slot in load_slots(doc, page_number, args):
        if slot.is_blank:
            continue
        left, top, right, bottom = art_box(slot.image)
        width, height = slot.image.size
        boxes.append((left / width, top / height, right / width, bottom / height))
    if not boxes:
        raise RuntimeError(f"reference page {page_number} has no non-blank cards")
    return tuple(float(value) for value in np.median(boxes, axis=0))


def select_slots(slots: list[Slot], count: int | None, page_number: int) -> list[Slot]:
    if count is None:
        wanted = sum(1 for slot in slots if not slot.is_blank)
        trailing_blanks = 0
        for slot in reversed(slots):
            if slot.is_blank:
                trailing_blanks += 1
            else:
                break
        if wanted != len(slots) - trailing_blanks:
            print(
                f"  warning: page {page_number} has blank cards before the end; "
                "auto count keeps only the leading run",
                file=sys.stderr,
            )
        count = len(slots) - trailing_blanks
    if count > len(slots):
        print(
            f"  warning: page {page_number} has {len(slots)} slots, "
            f"clamping requested {count}",
            file=sys.stderr,
        )
        count = len(slots)
    return slots[:count]


def report(doc: fitz.Document, pages: list[int], args) -> None:
    print(f"{'page':>5}  {'grid':>7}  {'slots':>5}  {'cards':>5}  blanks")
    for page_number in pages:
        slots = load_slots(doc, page_number, args)
        rows = max((slot.row for slot in slots), default=0)
        cols = max((slot.col for slot in slots), default=0)
        blanks = [slot.index for slot in slots if slot.is_blank]
        cards = len(slots) - len(blanks)
        blank_text = ",".join(str(i) for i in blanks) if blanks else "-"
        print(
            f"{page_number:>5}  {rows}x{cols:<5}  {len(slots):>5}  {cards:>5}  {blank_text}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cut individual card PNGs out of a card-sheet PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s cards.pdf --list\n"
            "  %(prog)s cards.pdf --pages 1,3,5 --count 16 --out out/dunwich\n"
            "  %(prog)s cards.pdf --pages 19,25 --count 19:11,25:7 --out out/misc\n"
            "  %(prog)s cards.pdf --pages 1-25/2 --count auto --out out/all\n"
        ),
    )
    parser.add_argument("pdf", type=Path, help="source PDF")
    parser.add_argument(
        "--pages",
        default="odd",
        help="pages to cut: odd, even, all, or e.g. 1,3,5-9,1-25/2 (default: odd)",
    )
    parser.add_argument(
        "--count",
        default="auto",
        help=(
            "cards to take per page in reading order: auto (skip blank slots), "
            "a single number, one number per page, or page:count pairs "
            "(default: auto)"
        ),
    )
    parser.add_argument("--out", type=Path, help="output folder for the PNGs")
    parser.add_argument("--prefix", default="card", help="filename prefix (default: card)")
    parser.add_argument(
        "--name",
        choices=("seq", "page"),
        default="seq",
        help="seq: card_001.png; page: card_p03_c07.png (default: seq)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "extract", "render"),
        default="auto",
        help="extract embedded card images, rasterise the page, or auto (default: auto)",
    )
    parser.add_argument("--rows", type=int, default=4, help="grid rows for render mode")
    parser.add_argument("--cols", type=int, default=4, help="grid columns for render mode")
    parser.add_argument("--dpi", type=int, default=300, help="render-mode DPI")
    parser.add_argument(
        "--no-trim",
        dest="trim",
        action="store_false",
        help="keep the gutter padding around each card",
    )
    parser.add_argument(
        "--ref-page",
        type=int,
        help=(
            "crop every card to the card rectangle measured on this page instead "
            "of to its own art; use a page of fronts when cutting bled card backs"
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="report the grid and blank slots per page, then exit",
    )
    parser.add_argument("--dry-run", action="store_true", help="list files without writing")
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing files in the output folder"
    )
    parser.add_argument("--manifest", action="store_true", help="also write manifest.csv")
    args = parser.parse_args()

    if not args.pdf.exists():
        parser.error(f"no such file: {args.pdf}")

    with fitz.open(args.pdf) as doc:
        try:
            pages = parse_pages(args.pages, doc.page_count)
        except ValueError as error:
            parser.error(str(error))
        if not pages:
            parser.error("--pages selected no pages")

        if args.list:
            report(doc, pages, args)
            return 0

        if args.out is None:
            parser.error("--out is required unless --list is given")
        try:
            counts = parse_counts(args.count, pages)
        except ValueError as error:
            parser.error(str(error))

        window = None
        if args.ref_page is not None:
            if not 1 <= args.ref_page <= doc.page_count:
                parser.error(f"--ref-page must be in 1..{doc.page_count}")
            window = measure_window(doc, args.ref_page, args)

        if not args.dry_run:
            args.out.mkdir(parents=True, exist_ok=True)

        records = []
        written = 0
        for page_number in pages:
            slots = load_slots(doc, page_number, args)
            chosen = select_slots(slots, counts[page_number], page_number)
            print(f"page {page_number}: {len(chosen)} of {len(slots)} slots")

            for slot in chosen:
                if args.name == "seq":
                    filename = f"{args.prefix}_{written + 1:03d}.png"
                else:
                    filename = f"{args.prefix}_p{slot.page:02d}_c{slot.index:02d}.png"
                target = args.out / filename
                if window is not None:
                    image = crop_to_window(slot.image, window)
                elif args.trim:
                    image = trim_border(slot.image)
                else:
                    image = slot.image

                if args.dry_run:
                    print(f"  {filename}  {image.width}x{image.height}")
                else:
                    if target.exists() and not args.force:
                        parser.error(f"{target} already exists; use --force to overwrite")
                    image.save(target)
                written += 1
                records.append(
                    {
                        "file": filename,
                        "page": slot.page,
                        "row": slot.row,
                        "col": slot.col,
                        "index": slot.index,
                        "width": image.width,
                        "height": image.height,
                    }
                )

        if args.manifest and not args.dry_run:
            manifest_path = args.out / "manifest.csv"
            with manifest_path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(records)
            print(f"wrote {manifest_path}")

        verb = "would write" if args.dry_run else "wrote"
        print(f"{verb} {written} card(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
