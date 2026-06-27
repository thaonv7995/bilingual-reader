#!/usr/bin/env python3
"""Extract figure regions from single-page source PDFs into PNG assets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz



FIGURE_RE = re.compile(r"^Figure\s+([A-Za-z\d]+(?:[-.]\d+)?)(?:\s|[:.]|$)", re.I)


def _figure_labels(page: fitz.Page) -> list[tuple[str, str, fitz.Rect]]:
    """Return (fig_id, label_line, bbox) sorted top-to-bottom."""
    found: list[tuple[str, str, fitz.Rect]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            parts = []
            line_rect: fitz.Rect | None = None
            for span in line.get("spans", []):
                parts.append(span.get("text", ""))
                r = fitz.Rect(span["bbox"])
                line_rect = r if line_rect is None else line_rect | r
            text = "".join(parts).strip()
            m = FIGURE_RE.match(text)
            if m and line_rect is not None:
                found.append((m.group(1), text, line_rect))
    found.sort(key=lambda x: x[2].y0)
    return found


def _footer_top(page: fitz.Page) -> float:
    """Y coordinate above footer/copyright band."""
    rect = page.rect
    for token in ("Copyright", "Robert C. Martin"):
        hits = page.search_for(token)
        if hits:
            return min(h.y0 for h in hits) - 4
    return rect.height - 48


def _drawing_band(page: fitz.Page, y0: float, y1: float) -> fitz.Rect | None:
    """Bounding box of vector drawings between y0 and y1."""
    band: fitz.Rect | None = None
    page_rect = page.rect
    for path in page.get_drawings():
        # Ignore text highlights: solid fills without stroke color, height 10-20pt
        if path.get("type") == "f" and path.get("color") is None:
            r = fitz.Rect(path["rect"])
            if 10 <= r.height <= 20:
                continue
        r = fitz.Rect(path["rect"])
        if (r.width > page_rect.width * 0.9) and (r.height > page_rect.height * 0.9):
            continue
        if r.y1 < y0 or r.y0 > y1:
            continue
        if r.width < 8 and r.height < 8:
            continue
        band = r if band is None else band | r
    return band


def _image_band(page: fitz.Page, y0: float, y1: float) -> fitz.Rect | None:
    """Bounding box of embedded images between y0 and y1."""
    band: fitz.Rect | None = None
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.y1 < y0 or r.y0 > y1:
            continue
        band = r if band is None else band | r
    return band


def _diagram_text_band(page: fitz.Page, y0: float, y1: float) -> fitz.Rect | None:
    """BBox of UML / diagram text lines in a vertical band."""
    markers = ("+ ", "- ", "«", "»", "void ", "class ", "struct ", "enum ")
    names = ("Ellipse", "Circle", "User", "Base", "Derived", "Modem", "Subject")
    band: fitz.Rect | None = None
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not text or len(text) > 80:
                continue
            if not (text.startswith(markers) or text in names or " : " in text):
                continue
            rect: fitz.Rect | None = None
            for span in line.get("spans", []):
                r = fitz.Rect(span["bbox"])
                rect = r if rect is None else rect | r
            if rect is None or rect.y1 < y0 or rect.y0 > y1:
                continue
            band = rect if band is None else band | rect
    return band


def _listing_top(page: fitz.Page, after_y: float) -> float | None:
    hits = page.search_for("Listing")
    below = [h for h in hits if h.y0 >= after_y - 2]
    return min(h.y0 for h in below) if below else None


def extract_figures(
    pdf_path: Path,
    out_dir: Path,
    *,
    page_num: int,
    dpi: int = 200,
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    with fitz.open(pdf_path) as doc:
        page = doc[0]
        rect = page.rect
        labels = _figure_labels(page)
        if page_num == 289:
            labels = [l for l in labels if l[0] != "an"]
        elif page_num == 375:
            labels = [l for l in labels if "shows the request flow" not in l[1]]
        
        # Fallback for pages that have hardcoded clips but no standard "Figure" text label
        hardcoded_pages = {
                3: [("1", "", fitz.Rect(45.5, 114.5, 572.5, 616.5))],
                4: [("1", "", fitz.Rect(325.0, 261.0, 600.0, 436.0)),
                    ("2", "", fitz.Rect(326.0, 408.5, 601.0, 583.0)),
                    ("3", "", fitz.Rect(45.0, 640.0, 160.0, 680.0))],
                5: [("1", "", fitz.Rect(210, 465, 292, 545))],
                7: [("1", "", fitz.Rect(70.5, 117.0, 532.5, 410.5))],
                13: [("1", "", fitz.Rect(200.0, 465.0, 420.0, 615.0))],
                14: [],
                15: [],
                16: [],
                17: [],
                18: [],
                19: [],
                21: [],
                22: [],
                23: [
                    ("1", "", fitz.Rect(254.0, 60.0, 575.5, 261.0)),
                    ("2", "", fitz.Rect(32.5, 248.5, 575.0, 574.0)),
                    ("3", "", fitz.Rect(34.5, 545.5, 321.0, 729.5))
                ],
                27: [("1", "", fitz.Rect(69, 317, 226, 452))],
                35: [("1", "", fitz.Rect(69, 317, 226, 452))],
                39: [("1", "", fitz.Rect(69, 317, 226, 452))],
                45: [("1", "", fitz.Rect(69, 317, 226, 452))],
                55: [("1", "", fitz.Rect(69, 317, 226, 452))],
                29: [("1.4", "Figure 1.4", fitz.Rect(28, 250, 548, 465)), ("1.5", "Figure 1.5", fitz.Rect(28, 35, 548, 170))],
                30: [("1.6", "Figure 1.6", fitz.Rect(28, 310, 548, 545))],
                31: [("1", "Figure 1", fitz.Rect(28, 415, 503, 585))],
                68: [("1", "Figure 1", fitz.Rect(28, 470, 503, 612))],
                69: [("1", "Figure 1", fitz.Rect(28, 290, 503, 605))],
                85: [("5.1", "Figure 5.1", fitz.Rect(28, 35, 548, 220))],
                87: [("1", "Figure 1", fitz.Rect(28, 110, 548, 345))],
                91: [("1", "Figure 1", fitz.Rect(28, 360, 503, 615))],
                92: [("1", "Figure 1", fitz.Rect(28, 390, 503, 568))],
                146: [("1", "Figure 1", fitz.Rect(95, 465, 285, 580))],
                164: [("1", "Figure 1", fitz.Rect(28, 35, 503, 336))],
                176: [("1", "Figure 1", fitz.Rect(50, 45, 480, 335))],
                190: [("1", "Figure 1", fitz.Rect(95, 455, 350, 605))],
                197: [("1", "Figure 1", fitz.Rect(91, 435, 467, 598))],
                198: [("1", "Figure 1", fitz.Rect(95, 50, 305, 255))],
                220: [("1", "Figure 1", fitz.Rect(101, 560, 474, 582))],
                244: [("1", "Figure 1", fitz.Rect(28, 476, 503, 576))],
                248: [("1", "Figure 1", fitz.Rect(28, 385, 503, 588))],
                241: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                257: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                277: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                355: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                469: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                289: [("10.8", "Figure 10.8", fitz.Rect(28, 50, 503, 144))],
                306: [("1", "Figure 1", fitz.Rect(100.0, 40.0, 488.0, 248.0))],
                307: [("1", "Figure 1", fitz.Rect(100.0, 40.0, 488.0, 335.0))],
                317: [("1", "Figure 1", fitz.Rect(90, 420, 360, 610))],
                336: [("1", "Figure 1", fitz.Rect(282, 420, 503, 615))],
                341: [("1", "Figure 1", fitz.Rect(28, 330, 503, 580))],
                349: [("15.1", "Figure 15.1. A navigation map for strategic distillation", fitz.Rect(106.5, 71.3, 481.5, 305.0))],
                368: [("1", "Figure 1", fitz.Rect(28, 48, 503, 216))],
                375: [("1", "Figure 1", fitz.Rect(28, 43.5, 548, 332.0))],
                383: [("1", "", fitz.Rect(52.5, 177.23, 318.0, 516.69))],
                384: [("1", "Figure 1", fitz.Rect(28, 50, 503, 135))],
                97: [("1", "", fitz.Rect(52, 123, 353, 350)), ("2", "", fitz.Rect(52, 382, 102, 396))],
                103: [("1", "", fitz.Rect(52, 123, 353, 325))],
                118: [("1", "", fitz.Rect(52, 123, 353, 440))],
                127: [("1", "", fitz.Rect(52, 123, 353, 422))],
                135: [("1", "", fitz.Rect(52, 123, 353, 441))],
                138: [("1", "", fitz.Rect(52, 43, 482, 165))],
                120: [("6.2", "Figure 6.2. Local versus global identity and object references", fitz.Rect(28, 35, 548, 215)), ("6.3", "Figure 6.3. AGGREGATE invariants", fitz.Rect(28, 301, 548, 562))],
                130: [("6.13", "", fitz.Rect(28, 35, 548, 290)), ("6.14", "Figure 6.14. A FACTORY METHOD spawns an ENTITY that is not part of the same AGGREGATE.", fitz.Rect(28, 495, 548, 735))],
                134: [("6.16", "", fitz.Rect(28, 65, 548, 272)), ("6.17", "Figure 6.17. Reconstituting an ENTITY transmitted as XML", fitz.Rect(28, 286, 548, 516))],
                143: [("1", "", fitz.Rect(28, 35, 548, 315))],
                162: [("1", "", fitz.Rect(100, 40, 488, 290))],
                402: [("1", "", fitz.Rect(52.5, 123.9, 308.25, 211.8))],
                405: [("16.20", "Figure 16.20. Each Employee Type is assigned a Retirement Plan.", fitz.Rect(28, 65, 548, 165))],
                166: [("7.8", "Figure 7.8. MODULES based on broad domain concepts", fitz.Rect(28, 35, 548, 510))],
                177: [("1", "", fitz.Rect(52, 129, 408, 409))],
                193: [("1", "", fitz.Rect(106.5, 58.578, 481.5, 366.488))],
                196: [("9.6", "Figure 9.6.", fitz.Rect(264, 372, 324, 383))],
                204: [("1", "", fitz.Rect(52.5, 171.9, 393.75, 223.1))],
                206: [("1", "", fitz.Rect(106.5, 43.5, 481.5, 186.5))],
                207: [("9.14", "Figure 9.14. A model applying a SPECIFICATION for validation", fitz.Rect(28.0, 168.0, 548.0, 350.0))],
                209: [("9.15", "Figure 9.15. The interaction between REPOSITORY and SPECIFICATION", fitz.Rect(100.0, 451.0, 488.0, 710.0))],
                213: [("1", "", fitz.Rect(106.5, 43.558, 481.5, 181.742))],
                227: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                229: [("1", "", fitz.Rect(28, 35, 548, 305))],
                233: [("10.10", "", fitz.Rect(106.5, 43.5, 481.5, 457.0))],
                237: [("1", "", fitz.Rect(28, 35, 548, 205)), ("10.13", "Figure 10.13.", fitz.Rect(258.0, 422.64, 330.85, 432.40))],
                249: [("1", "", fitz.Rect(106.5, 43.5, 481.5, 258.0))],
                267: [("1", "", fitz.Rect(106.5, 43.5, 481.5, 201.0))],
                276: [("1", "", fitz.Rect(52.5, 123.0, 427.5, 321.0))],
                278: [("12.2", "Figure 12.2. Options determined by choice of STRATEGY (POLICY) passed as argument", fitz.Rect(106.5, 43.5, 481.5, 262.85))],
                279: [("1", "", fitz.Rect(52.5, 123.0, 427.5, 326.0))],
                280: [("12.4", "Figure 12.4. A class diagram of a Route made up of Legs", fitz.Rect(28, 491.22, 548, 735.213))],
                282: [("12.7", "Figure 12.7. The elaborated class diagram of Route", fitz.Rect(28, 112.7, 548, 412.3)),
                      ("12.8", "Figure 12.8. A class diagram using COMPOSITE", fitz.Rect(28, 540.0, 548, 735.2))],
                283: [("12.9", "Figure 12.9. Instances representing a complete Route", fitz.Rect(28, 393.59, 548, 735.213))],
                297: [("14.1", "Figure 14.1. A navigation map for model integrity patterns", fitz.Rect(28, 35, 548, 245))],
                298: [("1", "", fitz.Rect(52.5, 183.0, 352.5, 416.5))],
                302: [("1", "", fitz.Rect(52.5, 109.17, 535.88, 358.05))],
                304: [("1", "", fitz.Rect(52.5, 123.9, 427.5, 316.9))],
                308: [("1", "", fitz.Rect(100.0, 40.0, 488.0, 215.0)), ("14.5", "Figure 14.5. Translation of a route found by the Network Traversal Service", fitz.Rect(100.0, 420.0, 488.0, 600.0))],
                313: [("1", "", fitz.Rect(52.5, 45.0, 536.25, 425.0))],
                315: [("1", "", fitz.Rect(52.5, 123.0, 352.5, 323.0))],
                319: [("1", "", fitz.Rect(52.5, 123.9, 159.0, 406.3))],
                322: [("1", "", fitz.Rect(52.5, 123.9, 352.5, 319.2))],
                327: [("1", "", fitz.Rect(52.5, 123.9, 352.5, 334.2))],
                334: [("14.11", "Figure 14.11. One context: crude integration", fitz.Rect(144.0, 673.9, 548.0, 686.0))],
                335: [("14.12", "Figure 14.12. One context: deeper model", fitz.Rect(28, 465, 548, 622))],
                350: [("1", "", fitz.Rect(52.5, 123.9, 396.75, 377.8))],
                376: [("1", "", fitz.Rect(106.5, 43.5, 481.5, 498.0))],
                379: [("1", "", fitz.Rect(52.5, 123.9, 297.0, 376.3))],
                391: [("1", "", fitz.Rect(106.5, 43.558, 481.5, 289.135))],
                398: [("16.12", "Figure 16.12. A typical interaction", fitz.Rect(106.5, 43.558, 481.5, 301.902))],
                411: [("16.25", "Figure 16.25. The user places a lot in the next machine and logs the move into the computer.", fitz.Rect(28.0, 78.0, 548.0, 356.0))],
                430: [("1", "", fitz.Rect(52.5, 493.0, 352.5, 700.0))],
                431: [("1", "", fitz.Rect(52.5, 295.0, 352.5, 502.0))],
                71: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                81: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                93: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                105: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                113: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                131: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                147: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                159: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                187: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                311: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                329: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                361: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                371: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                381: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                395: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                407: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                415: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                427: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                433: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                445: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                451: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                479: [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))],
                505: [
                    ("logo", "", fitz.Rect(201.0, 135.0, 223.5, 160.0)),
                    ("cover_how_linux_works", "", fitz.Rect(57.218, 168.0, 136.386, 273.015)),
                    ("cover_wicked_cool", "", fitz.Rect(189.492, 168.04, 268.932, 273.015)),
                    ("cover_cpp_crash", "", fitz.Rect(321.731, 168.055, 401.16, 273.015)),
                    ("cover_learn_robotics", "", fitz.Rect(57.218, 361.655, 136.647, 466.615)),
                    ("cover_eloquent_js", "", fitz.Rect(189.492, 361.615, 268.921, 466.574)),
                    ("cover_linux_basics", "", fitz.Rect(321.731, 361.6, 401.202, 466.615)),
                ]
        }
        if page_num in hardcoded_pages and "the-lean-startup" not in str(pdf_path):
            if "domain-driven-design" in str(pdf_path) and page_num in (197, 198):
                pass
            elif "the-linux-command-line" in str(pdf_path) and page_num in (197, 213, 227, 241, 257, 277, 311, 329, 355, 381, 407, 415, 427, 433, 445, 451, 469):
                labels = [("1", "", fitz.Rect(69.0, 317.0, 226.0, 452.0))]
            elif "the-linux-command-line" in str(pdf_path) and page_num == 336:
                labels = [("22.1", "Figure 22-1. Viewing a2ps output", fitz.Rect(121.5, 369.0, 454.15, 381.0))]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 5:
                labels = [
                    ("1", "", fitz.Rect(70.5, 120.0, 533.0, 415.5)),
                    ("2", "", fitz.Rect(70.5, 428.0, 533.0, 722.5))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 7:
                labels = [
                    ("1", "", fitz.Rect(70.5, 117.0, 532.5, 410.5))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 14:
                labels = [
                    ("1", "", fitz.Rect(49.5, 63.5, 553.5, 386.5)),
                    ("2", "", fitz.Rect(49.5, 388.5, 553.5, 710.0))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 18:
                labels = [
                    ("1", "", fitz.Rect(70.5, 65.0, 533.0, 385.5))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 19:
                labels = [
                    ("1", "", fitz.Rect(70.5, 65.0, 533.0, 381.0))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 15:
                labels = [
                    ("1", "", fitz.Rect(52.0, 100.0, 550.0, 405.0))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 16:
                labels = [
                    ("1", "", fitz.Rect(248.5, 108.0, 583.0, 316.5))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 17:
                labels = [
                    ("1", "", fitz.Rect(70.5, 329.0, 533.0, 623.5))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 21:
                labels = [
                    ("1", "", fitz.Rect(250.5, 94.0, 585.0, 302.5)),
                    ("2", "", fitz.Rect(250.5, 285.0, 585.0, 493.5)),
                    ("3", "", fitz.Rect(30.0, 488.5, 289.0, 702.5))
                ]
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 22:
                labels = [
                    ("1", "", fitz.Rect(43.0, 60.5, 293.0, 378.0)),
                    ("2", "", fitz.Rect(342.5, 157.5, 515.5, 330.5)),
                    ("3", "", fitz.Rect(42.0, 418.5, 279.0, 727.5)),
                    ("4", "", fitz.Rect(263.5, 418.5, 602.0, 727.5))
                ]
            elif "the-linux-command-line" in str(pdf_path):
                pass
            else:
                labels = hardcoded_pages[page_num]

        if "the-lean-startup" in str(pdf_path) and page_num == 26:
            labels = [("1", "", fitz.Rect(10, 0, 243, 184))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 27:
            labels = [("1", "", fitz.Rect(10, 0, 243, 188))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 28:
            labels = [("1", "", fitz.Rect(10, 0, 243, 187))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 33:
            labels = [
                ("1", "", fitz.Rect(49.92, 0.0, 202.56, 123.84)),
                ("2", "", fitz.Rect(30.0, 190.0, 250.0, 331.0))
            ]
        elif "the-lean-startup" in str(pdf_path) and page_num == 81:
            labels = [("1", "", fitz.Rect(10, 0, 242, 172))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 123:
            labels = [("1", "", fitz.Rect(10, 0, 243, 214))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 129:
            labels = [("1", "", fitz.Rect(5, 90, 247, 290))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 199:
            labels = [("1", "", fitz.Rect(10, 10, 242, 148))]
        elif "the-lean-startup" in str(pdf_path) and page_num == 207:
            labels = [("1", "", fitz.Rect(10, 155, 242, 304))]


        if not labels:
            return manifest

        footer_y = _footer_top(page)
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)

        margin_x = 28
        header_bottom = 50.0

        for i, (fig_id, label, caption_rect) in enumerate(labels):
            cap_y0 = caption_rect.y0
            cap_y1 = caption_rect.y1

            if i + 1 < len(labels):
                next_cap_y0 = labels[i + 1][2].y0
            else:
                next_cap_y0 = footer_y

            listing_y = _listing_top(page, cap_y1)
            prose_hits = page.search_for("In other words")
            prose_after = min((h.y0 for h in prose_hits if h.y0 > cap_y1), default=next_cap_y0)

            above_y0 = header_bottom if i == 0 else labels[i - 1][2].y1 + 4
            if page_num in (229, 238):
                above_y0 = 380.0
            above_y1 = cap_y0 - 2
            below_y0 = cap_y1 + 2
            below_y1 = min(
                next_cap_y0 - 4,
                listing_y - 4 if listing_y else next_cap_y0 - 4,
                prose_after - 4,
                footer_y,
            )

            art_above = None
            for band_func in (_drawing_band, _image_band, _diagram_text_band):
                res = band_func(page, above_y0, above_y1)
                if res:
                    art_above = res if art_above is None else art_above | res

            art_below = None
            for band_func in (_drawing_band, _image_band, _diagram_text_band):
                res = band_func(page, below_y0, below_y1)
                if res:
                    art_below = res if art_below is None else art_below | res

            def _gap_to_caption(art: fitz.Rect) -> float:
                if art.y1 <= cap_y0:
                    return cap_y0 - art.y1
                if art.y0 >= cap_y1:
                    return art.y0 - cap_y1
                return 0.0

            candidates: list[tuple[float, str, fitz.Rect]] = []
            if art_above:
                candidates.append((_gap_to_caption(art_above), "above", art_above))
            if art_below:
                candidates.append((_gap_to_caption(art_below), "below", art_below))
            if candidates:
                _, where, art = min(candidates, key=lambda x: x[0])
                if where == "above":
                    y0 = max(header_bottom, art.y0 - 8)
                    y1 = min(cap_y1 + 10, art.y1 + 10)
                else:
                    y0 = max(cap_y0 - 6, art.y0 - 8)
                    y1 = min(below_y1, art.y1 + 12)
            else:
                y0 = max(header_bottom, cap_y0 - 120)
                y1 = min(below_y1, cap_y1 + 80)

            # Always include caption lines in the crop.
            y0 = min(y0, cap_y0 - 4)
            y1 = max(y1, cap_y1 + 4)

            if y1 - y0 < 24:
                continue

            pix = None
            if page_num == 4:
                if fig_id == "1":
                    clip = fitz.Rect(325.0, 261.0, 600.0, 436.0)
                elif fig_id == "2":
                    clip = fitz.Rect(326.0, 408.5, 601.0, 583.0)
                elif fig_id == "3":
                    clip = fitz.Rect(45.0, 640.0, 160.0, 680.0)
            elif page_num == 3:
                clip = fitz.Rect(45.5, 114.5, 572.5, 616.5)
            elif page_num == 5:
                clip = fitz.Rect(210, 465, 292, 545)
            elif page_num == 7:
                clip = fitz.Rect(70.5, 117.0, 532.5, 410.5)
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 14:
                if fig_id == "1":
                    clip = fitz.Rect(49.5, 63.5, 553.5, 386.5)
                else:
                    clip = fitz.Rect(49.5, 388.5, 553.5, 710.0)
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 16:
                clip = fitz.Rect(248.5, 108.0, 583.0, 316.5)
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 22:
                if fig_id == "1":
                    clip = fitz.Rect(43.0, 60.5, 293.0, 378.0)
                elif fig_id == "2":
                    clip = fitz.Rect(342.5, 157.5, 515.5, 330.5)
                elif fig_id == "3":
                    clip = fitz.Rect(42.0, 418.5, 279.0, 727.5)
                else:
                    clip = fitz.Rect(263.5, 418.5, 602.0, 727.5)
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 23:
                if fig_id == "1":
                    clip = fitz.Rect(254.0, 60.0, 575.5, 261.0)
                elif fig_id == "2":
                    clip = fitz.Rect(32.5, 248.5, 575.0, 544.0)
                else:
                    clip = fitz.Rect(34.5, 552.0, 321.0, 715.0)
            elif "an-entire-mba-in-1-book" in str(pdf_path) and page_num == 18:
                clip = fitz.Rect(70.5, 65.0, 533.0, 385.5)
            elif "the-lean-startup" in str(pdf_path) and page_num in (26, 27, 28, 33, 81, 123, 129, 207):
                if page_num == 26:
                    clip = fitz.Rect(10, 0, 243, 184)
                elif page_num == 27:
                    clip = fitz.Rect(10, 0, 243, 188)
                elif page_num == 28:
                    clip = fitz.Rect(10, 0, 243, 187)
                elif page_num == 81:
                    clip = fitz.Rect(10, 0, 242, 172)
                elif page_num == 123:
                    clip = fitz.Rect(10, 0, 243, 214)
                elif page_num == 129:
                    clip = fitz.Rect(5, 90, 247, 290)
                elif page_num == 207:
                    clip = fitz.Rect(10, 150, 242, 305)
                elif page_num == 33:
                    if fig_id == "1":
                        clip = fitz.Rect(49.92, 0.0, 202.56, 123.84)
                    else:
                        clip = fitz.Rect(30.0, 190.0, 250.0, 331.0)
            elif page_num == 29:
                if fig_id == "1.4":
                    clip = fitz.Rect(28, 250, 548, 465)
                elif fig_id == "1.5":
                    # Special case: Figure 1.5 diagram is on page 30!
                    page30_path = pdf_path.parent.parent / "page_0030" / "source.pdf"
                    if page30_path.is_file():
                        with fitz.open(page30_path) as doc30:
                            page30 = doc30[0]
                            clip = fitz.Rect(28, 35, 548, 170)
                            pix = page30.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
            elif page_num == 30:
                if fig_id == "1.6":
                    clip = fitz.Rect(28, 310, 548, 545)
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 31:
                clip = fitz.Rect(28, 415, 503, 585)
            elif page_num == 237:
                if fig_id == "1":
                    clip = fitz.Rect(28, 35, 548, 205)
                else:
                    clip = fitz.Rect(28, 418, 548, 735)
            elif page_num == 146:
                clip = fitz.Rect(95, 465, 285, 580)
            elif page_num == 143:
                clip = fitz.Rect(28, 35, 548, 315)
            elif page_num == 405:
                clip = fitz.Rect(28, 65, 548, 165)
            elif page_num == 176:
                clip = fitz.Rect(50, 45, 480, 335)
            elif page_num == 68:
                clip = fitz.Rect(28, 470, 503, 612)
            elif page_num == 69:
                clip = fitz.Rect(28, 290, 503, 605)
            elif page_num == 85:
                if fig_id == "5.1":
                    page86_path = pdf_path.parent.parent / "page_0086" / "source.pdf"
                    if page86_path.is_file():
                        with fitz.open(page86_path) as doc86:
                            page86 = doc86[0]
                            clip = fitz.Rect(28, 35, 548, 220)
                            pix = page86.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 272:
                if fig_id == "11.10":
                    page273_path = pdf_path.parent.parent / "page_0273" / "source.pdf"
                    if page273_path.is_file():
                        with fitz.open(page273_path) as doc273:
                            page273 = doc273[0]
                            clip = fitz.Rect(28, 35, 548, 205)
                            pix = page273.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 155:
                if fig_id == "7.3":
                    page156_path = pdf_path.parent.parent / "page_0156" / "source.pdf"
                    if page156_path.is_file():
                        with fitz.open(page156_path) as doc156:
                            page156 = doc156[0]
                            clip = fitz.Rect(28, 35, 548, 340)
                            pix = page156.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 280:
                if fig_id == "12.4":
                    page281_path = pdf_path.parent.parent / "page_0281" / "source.pdf"
                    if page281_path.is_file():
                        with fitz.open(page281_path) as doc281:
                            page281 = doc281[0]
                            clip = fitz.Rect(28, 35, 548, 358)
                            pix = page281.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 282:
                if fig_id == "12.8":
                    page283_path = pdf_path.parent.parent / "page_0283" / "source.pdf"
                    if page283_path.is_file():
                        with fitz.open(page283_path) as doc283:
                            page283 = doc283[0]
                            clip = fitz.Rect(28, 35, 548, 308)
                            pix = page283.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 283:
                if fig_id == "12.9":
                    page284_path = pdf_path.parent.parent / "page_0284" / "source.pdf"
                    if page284_path.is_file():
                        with fitz.open(page284_path) as doc284:
                            page284 = doc284[0]
                            clip = fitz.Rect(28, 35, 548, 380)
                            pix = page284.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                    else:
                        clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                        clip &= rect
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 87:
                clip = fitz.Rect(28, 110, 548, 345)
            elif page_num == 91:
                clip = fitz.Rect(28, 110, 503, 315)
            elif page_num == 92:
                clip = fitz.Rect(28, 390, 503, 568)
            elif page_num == 505:
                if fig_id == "logo":
                    clip = fitz.Rect(201.0, 135.0, 222.8, 159.0)
                elif fig_id == "cover_how_linux_works":
                    clip = fitz.Rect(57.218, 168.0, 136.386, 273.015)
                elif fig_id == "cover_wicked_cool":
                    clip = fitz.Rect(189.492, 168.04, 268.932, 273.015)
                elif fig_id == "cover_cpp_crash":
                    clip = fitz.Rect(321.731, 168.055, 401.16, 273.015)
                elif fig_id == "cover_learn_robotics":
                    clip = fitz.Rect(57.218, 361.655, 136.647, 466.615)
                elif fig_id == "cover_eloquent_js":
                    clip = fitz.Rect(189.492, 361.615, 268.921, 466.574)
                elif fig_id == "cover_linux_basics":
                    clip = fitz.Rect(321.731, 361.6, 401.202, 466.615)
            elif page_num == 97:
                if fig_id == "1":
                    clip = fitz.Rect(52, 123, 353, 350)
                elif fig_id == "2":
                    clip = fitz.Rect(52, 382, 102, 396)
            elif page_num == 103:
                clip = fitz.Rect(52, 123, 353, 325)
            elif page_num == 127:
                clip = fitz.Rect(52, 123, 353, 422)
            elif page_num == 135:
                clip = fitz.Rect(52, 123, 353, 441)
            elif page_num == 120:
                if fig_id == "6.2":
                    clip = fitz.Rect(28, 35, 548, 215)
                elif fig_id == "6.3":
                    clip = fitz.Rect(28, 301, 548, 562)
            elif page_num == 134:
                if fig_id == "6.16":
                    clip = fitz.Rect(28, 65, 548, 272)
                elif fig_id == "6.17":
                    clip = fitz.Rect(28, 286, 548, 516)
            elif page_num == 190:
                clip = fitz.Rect(95, 455, 350, 605)
            elif page_num == 289:
                if fig_id == "10.8":
                    clip = fitz.Rect(28, 50, 503, 144)
                else:
                    clip = fitz.Rect(28, 415, 503, 580)
            elif page_num == 306:
                clip = fitz.Rect(100.0, 40.0, 488.0, 248.0)
            elif page_num == 307:
                clip = fitz.Rect(100.0, 40.0, 488.0, 335.0)
            elif page_num == 309:
                if fig_id == "14.6":
                    clip = fitz.Rect(100.0, 120.0, 488.0, 226.0)
                else:
                    clip = fitz.Rect(100.0, 308.0, 488.0, 568.0)
            elif page_num == 317:
                clip = fitz.Rect(90, 420, 360, 610)
            elif page_num == 319:
                clip = fitz.Rect(52.5, 123.9, 159.0, 406.3)
            elif page_num == 313:
                clip = fitz.Rect(52.5, 48.0, 536.25, 420.0)
            elif page_num == 334:
                if fig_id == "14.11":
                    page335_path = pdf_path.parent.parent / "page_0335" / "source.pdf"
                    if page335_path.is_file():
                        with fitz.open(page335_path) as doc335:
                            page335 = doc335[0]
                            clip = fitz.Rect(106.5, 43.5, 481.5, 242.0)
                            pix = page335.get_pixmap(matrix=matrix, clip=clip, alpha=False)
            elif page_num == 400:
                if fig_id == "16.14":
                    page401_path = pdf_path.parent.parent / "page_0401" / "source.pdf"
                    if page401_path.is_file():
                        with fitz.open(page401_path) as doc401:
                            page401 = doc401[0]
                            clip = fitz.Rect(106.5, 43.558, 481.5, 240.32)
                            pix = page401.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 336:
                if "the-linux-command-line" in str(pdf_path):
                    clip = fitz.Rect(28, 158, 476, 385)
                else:
                    clip = fitz.Rect(282, 420, 503, 615)
            elif page_num == 384:
                clip = fitz.Rect(28, 50, 503, 135)
            elif page_num == 164:
                clip = fitz.Rect(28, 35, 503, 336)
            elif page_num == 297:
                clip = fitz.Rect(28, 35, 548, 245)
            elif page_num == 298:
                clip = fitz.Rect(52.5, 183.0, 352.5, 416.5)
            elif page_num == 335:
                clip = fitz.Rect(28, 465, 548, 622)
            elif page_num == 350:
                clip = fitz.Rect(52.5, 123.9, 396.75, 377.8)
            elif page_num == 302:
                clip = fitz.Rect(52.5, 109.17, 535.88, 358.05)
            elif page_num == 304:
                clip = fitz.Rect(52.5, 123.9, 427.5, 316.9)
            elif page_num == 308:
                if fig_id == "1":
                    clip = fitz.Rect(100.0, 40.0, 488.0, 215.0)
                else:
                    clip = fitz.Rect(100.0, 420.0, 488.0, 600.0)
            elif page_num == 198 and "domain-driven-design" not in str(pdf_path):
                clip = fitz.Rect(95, 50, 305, 255)
            elif page_num == 197 and "domain-driven-design" not in str(pdf_path):
                if "the-linux-command-line" in str(pdf_path):
                    clip = fitz.Rect(69.0, 317.0, 226.0, 452.0)
                else:
                    clip = fitz.Rect(91, 435, 467, 598)
            elif page_num == 375:
                clip = fitz.Rect(28, 43.5, 548, 332.0)
            elif page_num == 376:
                clip = fitz.Rect(106.5, 43.5, 481.5, 498.0)
            elif page_num == 379:
                clip = fitz.Rect(52.5, 123.9, 297.0, 376.3)
            elif page_num == 383:
                clip = fitz.Rect(52.5, 177.23, 318.0, 516.69)
            elif page_num == 391:
                clip = fitz.Rect(106.5, 43.558, 481.5, 289.135)
            elif page_num == 398:
                clip = fitz.Rect(106.5, 43.558, 481.5, 301.902)
            elif page_num == 220:
                clip = fitz.Rect(101, 560, 474, 582)
            elif page_num == 229:
                clip = fitz.Rect(28, 35, 548, 305)
            elif page_num == 244:
                clip = fitz.Rect(28, 476, 503, 576)
            elif page_num == 248:
                clip = fitz.Rect(28, 385, 503, 588)
            elif page_num == 249:
                clip = fitz.Rect(106.5, 43.5, 481.5, 258.0)
            elif page_num == 267:
                clip = fitz.Rect(106.5, 43.5, 481.5, 201.0)
            elif page_num == 276:
                clip = fitz.Rect(52.5, 123.0, 427.5, 321.0)
            elif page_num == 278:
                clip = fitz.Rect(106.5, 43.5, 481.5, 262.85)
            elif page_num == 279:
                clip = fitz.Rect(52.5, 123.0, 427.5, 326.0)
            elif page_num == 341:
                clip = fitz.Rect(28, 330, 503, 580)
            elif page_num == 349:
                clip = fitz.Rect(106.5, 71.3, 481.5, 305.0)
            elif page_num == 368:
                clip = fitz.Rect(28, 48, 503, 216)
            elif page_num == 138:
                clip = fitz.Rect(52, 43, 482, 165)
            elif page_num == 162:
                clip = fitz.Rect(100, 40, 488, 290)
            elif page_num == 166:
                clip = fitz.Rect(28, 35, 548, 510)
            elif page_num == 193:
                clip = fitz.Rect(106.5, 58.578, 481.5, 366.488)
            elif page_num == 196:
                clip = fitz.Rect(28, 365, 548, 610)
            elif page_num == 207:
                clip = fitz.Rect(28, 168, 548, 350)
            elif page_num == 209:
                clip = fitz.Rect(95, 202, 492, 470)
            elif page_num == 213 and "the-linux-command-line" not in str(pdf_path):
                clip = fitz.Rect(100, 35, 488, 190)
            elif page_num == 233:
                clip = fitz.Rect(106.5, 43.5, 481.5, 457.0)
            elif page_num == 417:
                if fig_id == "17.2":
                    page418_path = pdf_path.parent.parent / "page_0418" / "source.pdf"
                    if page418_path.is_file():
                        with fitz.open(page418_path) as doc418:
                            page418 = doc418[0]
                            clip = fitz.Rect(106.5, 43.5, 481.5, 239.0)
                            pix = page418.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 418:
                if fig_id == "17.4":
                    page419_path = pdf_path.parent.parent / "page_0419" / "source.pdf"
                    if page419_path.is_file():
                        with fitz.open(page419_path) as doc419:
                            page419 = doc419[0]
                            clip = fitz.Rect(106.5, 43.5, 481.5, 310.0)
                            pix = page419.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                else:
                    clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                    clip &= rect
            elif page_num == 15:
                clip = fitz.Rect(52.0, 100.0, 550.0, 405.0)
            elif page_num == 21:
                if fig_id == "1":
                    clip = fitz.Rect(250.5, 94.0, 585.0, 302.5)
                elif fig_id == "2":
                    clip = fitz.Rect(250.5, 285.0, 585.0, 493.5)
                elif fig_id == "3":
                    clip = fitz.Rect(30.0, 488.5, 289.0, 702.5)
            elif page_num == 430:
                clip = fitz.Rect(52.5, 493.0, 352.5, 700.0)
            elif page_num == 431:
                clip = fitz.Rect(52.5, 295.0, 352.5, 502.0)
            elif page_num in (27, 35, 45, 55, 71, 81, 93, 105, 113, 131, 147, 159, 213, 227, 311, 329, 361, 371, 381, 395, 407, 415, 427, 433, 445, 451, 479):
                clip = fitz.Rect(69.0, 317.0, 226.0, 452.0)
            else:
                clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
                clip &= rect
            safe_id = fig_id.replace("-", "_").replace(".", "_")
            name = f"page_{page_num:04d}_fig_{safe_id}.png"
            out_path = out_dir / name

            pix_width, pix_height = None, None
            if out_path.is_file():
                try:
                    import struct
                    with open(out_path, "rb") as img_f:
                        img_data = img_f.read(24)
                        if len(img_data) >= 24 and img_data[12:16] == b"IHDR":
                            pix_width, pix_height = struct.unpack(">II", img_data[16:24])
                except Exception:
                    pass

            if pix_width is None or pix_height is None or page_num == 93:
                if pix is None:
                    if page_num in (4, 15, 27, 35, 45, 71, 93, 213, 227, 311, 329, 361, 371, 381, 395, 407, 415, 427, 445, 451, 479):
                        for block in page.get_text("dict")["blocks"]:
                            if block["type"] == 0:
                                for line in block["lines"]:
                                    for span in line["spans"]:
                                        page.add_redact_annot(span["bbox"])
                        page.apply_redactions(images=0, graphics=0)
                    pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
                pix.save(str(out_path))
                pix_width, pix_height = pix.width, pix.height

            manifest.append(
                {
                    "figure": fig_id,
                    "label": label,
                    "file": f"images/{name}",
                    "width": pix_width,
                    "height": pix_height,
                    "clip": [clip.x0, clip.y0, clip.x1, clip.y1],
                }
            )
    return manifest


def process_book(book_root: Path, pages: list[int] | None = None) -> dict:
    work = book_root / "work"
    assets = book_root / "output" / "assets" / "images"
    manifest_path = book_root / "output" / "assets" / "figures.manifest.json"
    all_manifest: dict[str, list] = {}
    if manifest_path.is_file():
        all_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    targets: list[int] = []
    if pages:
        targets = pages
    else:
        for d in sorted(work.glob("page_*/source.pdf")):
            targets.append(int(d.parent.name.split("_")[1]))

    for n in sorted(targets):
        pdf = work / f"page_{n:04d}" / "source.pdf"
        if not pdf.is_file():
            continue
        figs = extract_figures(pdf, assets, page_num=n)
        if figs:
            all_manifest[f"page_{n:04d}"] = figs
            print(f"page {n:04d}: {len(figs)} figure(s)")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(all_manifest, indent=2), encoding="utf-8")
    return all_manifest


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: extract_pdf_figures.py <book-root> [page ...]", file=sys.stderr)
        return 2
    book = Path(argv[1]).resolve()
    pages = [int(x) for x in argv[2:]] if len(argv) > 2 else None
    process_book(book, pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
