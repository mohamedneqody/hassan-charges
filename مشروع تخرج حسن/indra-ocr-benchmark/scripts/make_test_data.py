#!/usr/bin/env python3
"""Generate OCR test samples with known ground truth for the Indra OCR benchmark.

Creates:
  test_data/images/en_printed.png    - printed English text (lossless PNG)
  test_data/images/ar_printed.png    - printed Arabic text (lossless PNG)
  test_data/images/mixed_ar_en.png   - mixed Arabic + English lines
  test_data/images/table.png         - simple grid table (Arabic header + rows)
  test_data/pdfs/searchable.pdf      - 2-page PDF with a real text layer (ASCII)
  test_data/pdfs/scanned.pdf         - image-only PDF (en + ar pages, no text layer)
  test_data/pdfs/bench_40p.pdf       - 40-page image-only PDF for speed tests
  test_data/pdfs/warmup_1p.pdf       - 1-page image-only PDF for warm-up
  test_data/ground_truth.json        - exact source text of every sample

Run inside the WSL venv: python scripts/make_test_data.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import arabic_reshaper
import img2pdf
from bidi.algorithm import get_display
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont, features

HAS_RAQM = features.check("raqm")  # Pillow with libraqm does bidi+shaping itself


def has_arabic(s: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F" or "\uFB50" <= c <= "\uFDFF" or "\uFE70" <= c <= "\uFEFC" for c in s)


def viz(text: str) -> str:
    """String to hand to PIL. With Raqm: raw logical text (it shapes+bidi).
    Without Raqm: manual reshaping + visual reordering."""
    if HAS_RAQM:
        return text
    return get_display(arabic_reshaper.reshape(text)) if has_arabic(text) else text


def dir_kwargs(text: str) -> dict:
    return {"direction": "rtl"} if HAS_RAQM and has_arabic(text) else {}

PROJ = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
IMG_DIR = PROJ / "test_data" / "images"
PDF_DIR = PROJ / "test_data" / "pdfs"
GT_PATH = PROJ / "test_data" / "ground_truth.json"

W, H = 1654, 2339  # A4 @ 200 dpi
MARGIN_X = 130
MARGIN_TOP = 170
LINE_SPACING = 1.75
DPI = (200, 200)

LATIN_FONTS = [
    "/mnt/c/Windows/Fonts/arial.ttf",
    "/mnt/c/Windows/Fonts/times.ttf",
    "/mnt/c/Windows/Fonts/calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
ARABIC_FONTS = [
    "/mnt/c/Windows/Fonts/arial.ttf",
    "/mnt/c/Windows/Fonts/times.ttf",
    "/mnt/c/Windows/Fonts/tahoma.ttf",
    "/mnt/c/Windows/Fonts/segoeui.ttf",
]


def load_font(candidates: list[str], size: int, need_arabic: bool) -> tuple[ImageFont.FreeTypeFont, str]:
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, size)
        except Exception:
            continue
        if not need_arabic:
            return font, path
        # Probe Arabic coverage: two different Arabic letters must render
        # differently; a font without Arabic draws identical tofu boxes.
        import hashlib

        hashes = set()
        for ch in ("ب", "ل", "ع"):
            img = Image.new("L", (140, 140), 255)
            ImageDraw.Draw(img).text((30, 30), viz(ch), font=font, fill=0, **dir_kwargs(ch))
            hashes.add(hashlib.md5(img.tobytes()).hexdigest())
        if len(hashes) == 3:
            return font, path
    raise RuntimeError(f"no suitable font found (need_arabic={need_arabic})")


def render_page_lines(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    out_path: Path,
    rtl: bool = False,
    shape: bool = False,
    bold_first: bool = False,
) -> None:
    """Render each line on its own baseline. GT stores the logical string."""
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    y = MARGIN_TOP
    for i, ln in enumerate(lines):
        f = font
        if bold_first and i == 0:
            f = font_bold  # global set by caller
        tl = d.textlength(viz(ln), font=f, **dir_kwargs(ln))
        x = (W - MARGIN_X - tl) if rtl else MARGIN_X
        d.text((x, y), viz(ln), font=f, fill=0, **dir_kwargs(ln))
        y += int(f.size * LINE_SPACING)
    img.save(out_path, dpi=DPI)
    print(f"wrote {out_path.name} ({out_path.stat().st_size // 1024} KB)")


def make_searchable_pdf(pages_lines: list[list[str]], out_path: Path) -> None:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(25, 25, 25)
    for lines in pages_lines:
        pdf.add_page()
        pdf.set_font("Helvetica", size=13)
        for ln in lines:
            pdf.multi_cell(0, 8, ln, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(out_path))
    print(f"wrote {out_path.name} ({out_path.stat().st_size // 1024} KB)")


def images_to_pdf(png_paths: list[Path], out_path: Path, jpeg_quality: int = 90) -> None:
    """Bundle rendered page images into an image-only PDF (no text layer)."""
    buffers = []
    for p in png_paths:
        im = Image.open(p).convert("L")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=jpeg_quality, dpi=DPI)
        buffers.append(buf.getvalue())
    with open(out_path, "wb") as f:
        f.write(img2pdf.convert(buffers))
    print(f"wrote {out_path.name} ({out_path.stat().st_size // 1024} KB, {len(buffers)} pages)")


# --------------------------------------------------------------------------- #
# Sample content
# --------------------------------------------------------------------------- #

EN_LINES = [
    "The Industrial Revolution transformed manufacturing across Europe in the nineteenth",
    "century, replacing manual labor with steam-powered machinery in almost every sector.",
    "Modern factories now rely on automated systems and computer vision for quality control.",
    "Financial statements must be audited carefully before the annual report is submitted",
    "to shareholders and published on the official website of the stock exchange.",
    "Accurate data extraction from documents remains a fundamental challenge for",
    "enterprise software, and optical character recognition is at the center of it.",
]

AR_LINES = [
    "يشهد العالم اليوم تطورا سريعا في مجال الذكاء الاصطناعي وتقنيات معالجة اللغة الطبيعية.",
    "تعتمد المؤسسات المالية على أنظمة حديثة لتحليل القوائم المالية واستخراج البيانات منها.",
    "تسعى الشركات إلى أتمتة عمليات المراجعة والتدقيق لتوفير الوقت وتقليل الأخطاء البشرية.",
    "تعتبر مدينة القاهرة من أكبر مدن العالم العربي من حيث عدد السكان والمساحة الكلية.",
    "يجب على الموظف تسليم التقرير الشهري إلى المدير قبل نهاية الأسبوع الجاري على الأقل.",
    "تساهم المعالجة الآلية للمستندات في تحسين جودة القرارات وتسريع إجراءات العمل اليومية.",
    "يحتاج الباحثون إلى أدوات دقيقة لقراءة المخطوطات القديمة وحفظ النصوص في قواعد البيانات.",
]

MIXED_LINES = [
    "Annual Financial Report 2024",
    "التقرير المالي السنوي لعام 2024",
    "Total Revenue: 1,250,000 USD",
    "إجمالي الإيرادات: 1,250,000 دولار أمريكي",
    "Contact us at info@example.com or call +20 100 555 1234",
    "للتواصل والاستفسار يرجى زيارة مكتبنا في شارع التحرير، القاهرة",
    "Page prepared by the Document Processing Team",
]

TABLE_HEADER = ["الصنف", "الكمية", "سعر الوحدة", "الإجمالي"]
TABLE_ROWS = [
    ["قمح", "120", "350.50", "42060.00"],
    ["شعير", "80", "275.00", "22000.00"],
    ["Rice", "60", "410.25", "24615.00"],
    ["زيت ذرة", "45", "520.75", "23433.75"],
    ["سكر", "200", "48.90", "9780.00"],
]

BENCH_SENTENCES = [
    "The quarterly revenue increased by twelve percent following the launch of the new product line.",
    "Automated document processing reduces manual data entry costs for large enterprises significantly.",
    "Machine learning models require careful validation before deployment in production environments.",
    "The supply chain disruption affected delivery schedules across three regional distribution centers.",
    "Researchers published a detailed study on optical character recognition for historical archives.",
    "Energy consumption in modern data centers continues to grow despite improvements in efficiency.",
    "The city council approved the construction of a new public library near the central station.",
    "Investors reacted calmly to the announcement and the stock price remained stable all week.",
    "Effective communication between departments improves overall productivity and employee morale.",
    "The new encryption standard protects sensitive customer data against emerging cyber threats.",
    "Agricultural exports from the region doubled after the irrigation project was completed.",
    "Public health officials recommended regular exercise and balanced nutrition for all age groups.",
    "The railway connection between the two cities shortened travel time by nearly two hours.",
    "Software developers adopted new testing frameworks to catch critical bugs earlier in the cycle.",
]

BENCH_PAGES = 40
LINES_PER_PAGE = 7


def draw_table(font_ar: ImageFont.FreeTypeFont, font_lat: ImageFont.FreeTypeFont, out_path: Path) -> None:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    col_w = [430, 260, 340, 340]
    table_w = sum(col_w)
    x0 = (W - table_w) // 2
    y0 = 320
    row_h = 100

    def cell_text(cx, cy, cw, text, font, rtl_shape=True):
        tl = d.textlength(viz(text), font=font, **dir_kwargs(text))
        d.text((cx + (cw - tl) / 2, cy + (row_h - font.size) / 2 - 4), viz(text), font=font, fill=0, **dir_kwargs(text))

    # header
    cx = x0
    for w, text in zip(col_w, TABLE_HEADER):
        cell_text(cx, y0, w, text, font_ar)
        cx += w
    # rows
    for r, row in enumerate(TABLE_ROWS):
        cy = y0 + (r + 1) * row_h
        cx = x0
        for w, text in zip(col_w, row):
            font = font_lat if all(ord(c) < 0x0590 for c in text) else font_ar
            cell_text(cx, cy, w, text, font, rtl_shape=not all(ord(c) < 0x0590 for c in text))
            cx += w
    # grid
    n_rows = len(TABLE_ROWS) + 1
    for r in range(n_rows + 1):
        yy = y0 + r * row_h
        d.line([(x0, yy), (x0 + table_w, yy)], fill=0, width=3)
    cx = x0
    for w in col_w + [0]:
        d.line([(cx, y0), (cx, y0 + n_rows * row_h)], fill=0, width=3)
        cx += w
    img.save(out_path, dpi=DPI)
    print(f"wrote {out_path.name} ({out_path.stat().st_size // 1024} KB)")


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    font_ar30, ar_font_path = load_font(ARABIC_FONTS, 30, need_arabic=True)
    font_lat30, lat_font_path = load_font(LATIN_FONTS, 30, need_arabic=False)
    print(f"PIL raqm layout engine: {HAS_RAQM}")
    print(f"Arabic font: {ar_font_path}")
    print(f"Latin  font: {lat_font_path}")

    gt: dict = {}

    # 1. English printed image
    render_page_lines(EN_LINES, font_lat30, IMG_DIR / "en_printed.png")
    gt["en_printed"] = {
        "path": "test_data/images/en_printed.png",
        "language": "en",
        "pages": [{"lines": EN_LINES, "text": "\n".join(EN_LINES)}],
    }

    # 2. Arabic printed image (rendered shaped+visual, GT logical)
    render_page_lines(AR_LINES, font_ar30, IMG_DIR / "ar_printed.png", rtl=True, shape=True)
    gt["ar_printed"] = {
        "path": "test_data/images/ar_printed.png",
        "language": "ar",
        "pages": [{"lines": AR_LINES, "text": "\n".join(AR_LINES)}],
    }

    # 3. Mixed Arabic/English image
    render_page_lines(MIXED_LINES, font_ar30, IMG_DIR / "mixed_ar_en.png", shape=True)
    gt["mixed_ar_en"] = {
        "path": "test_data/images/mixed_ar_en.png",
        "language": "ar+en",
        "pages": [{"lines": MIXED_LINES, "text": "\n".join(MIXED_LINES)}],
    }

    # 4. Table image
    global font_bold
    try:
        font_bold = ImageFont.truetype(ar_font_path.replace("arial.ttf", "arialbd.ttf"), 30)
    except Exception:
        font_bold = font_ar30
    draw_table(font_ar30, font_lat30, IMG_DIR / "table.png")
    table_lines = ["  |  ".join(TABLE_HEADER)] + ["  |  ".join(r) for r in TABLE_ROWS]
    gt["table"] = {
        "path": "test_data/images/table.png",
        "language": "ar+en",
        "header": TABLE_HEADER,
        "rows": TABLE_ROWS,
        "pages": [{"lines": table_lines, "text": "\n".join(table_lines)}],
    }

    # 5. Searchable PDF (real text layer, ASCII so Helvetica maps 1:1)
    searchable_pages = [EN_LINES[:4], EN_LINES[4:]]
    make_searchable_pdf(searchable_pages, PDF_DIR / "searchable.pdf")
    gt["searchable_pdf"] = {
        "path": "test_data/pdfs/searchable.pdf",
        "language": "en",
        "pages": [{"lines": ls, "text": "\n".join(ls)} for ls in searchable_pages],
    }

    # 6. Scanned PDF: en page + ar page, image-only
    images_to_pdf([IMG_DIR / "en_printed.png", IMG_DIR / "ar_printed.png"], PDF_DIR / "scanned.pdf")
    gt["scanned_pdf"] = {
        "path": "test_data/pdfs/scanned.pdf",
        "language": "en+ar",
        "pages": [
            {"lines": EN_LINES, "text": "\n".join(EN_LINES)},
            {"lines": AR_LINES, "text": "\n".join(AR_LINES)},
        ],
    }

    # 7. Benchmark PDF: 40 image-only pages, deterministic content
    bench_page_pngs = []
    bench_gt_pages = []
    for n in range(BENCH_PAGES):
        lines = [BENCH_SENTENCES[(n * 3 + k) % len(BENCH_SENTENCES)] for k in range(LINES_PER_PAGE)]
        png = IMG_DIR / f"_bench_p{n:03d}.png"
        render_page_lines(lines, font_lat30, png)
        bench_page_pngs.append(png)
        bench_gt_pages.append({"lines": lines, "text": "\n".join(lines)})
    images_to_pdf(bench_page_pngs, PDF_DIR / "bench_40p.pdf", jpeg_quality=88)
    gt["bench_40p"] = {
        "path": "test_data/pdfs/bench_40p.pdf",
        "language": "en",
        "pages": bench_gt_pages,
    }

    # warm-up single page
    warm_lines = [BENCH_SENTENCES[k] for k in range(3)]
    warm_png = IMG_DIR / "_warmup.png"
    render_page_lines(warm_lines, font_lat30, warm_png)
    images_to_pdf([warm_png], PDF_DIR / "warmup_1p.pdf", jpeg_quality=88)
    warm_png.unlink()
    for p in bench_page_pngs:
        p.unlink()

    GT_PATH.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote ground_truth.json ({GT_PATH.stat().st_size // 1024} KB)")

    # Verify text layers honestly
    try:
        import pypdfium2 as pdfium

        for name in ("searchable.pdf", "scanned.pdf"):
            doc = pdfium.PdfDocument(str(PDF_DIR / name))
            total_chars = 0
            for pg in doc:
                tp = pg.get_textpage()
                try:
                    txt = tp.get_text_bounded()
                except Exception:
                    txt = tp.get_text_range()
                total_chars += len(txt.strip())
            print(f"text-layer chars in {name}: {total_chars}")
            doc.close()
    except Exception as exc:  # pragma: no cover
        print(f"pdfium text-layer check failed: {exc}")

    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
