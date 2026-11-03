"""Export every figure of scripts/report/d2d_report.html as a PNG, plus page previews of both PDFs.
Each SVG diagram and bar chart is printed on its own page with headless Edge/Chrome, rasterized
with PyMuPDF and trimmed. Output: docs/images/*.png, docs/images/report/page-NN.png,
docs/images/explainer/page-N.png.
Usage (Windows host, needs Edge or Chrome, pymupdf, pillow):
  python scripts/report/export_figures.py
"""
import io
import os
import pathlib
import re
import subprocess
import tempfile

import pymupdf
from PIL import Image, ImageChops

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "scripts" / "report" / "d2d_report.html"
OUT = ROOT / "docs" / "images"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
EXE = next(b for b in BROWSERS if os.path.exists(b))

# SVG diagrams in document order (the 24x24 logo is skipped), with the width each is drawn at.
SVG_NAMES = [
    ("system_overview", 1000), ("workflow", 1100), ("chiplets", 640), ("architecture", 1100),
    ("flit_layout", 1100), ("lane_beats", 640), ("link_layer", 1100), ("go_back_n", 620),
    ("replay_buffer", 640), ("credits", 640), ("ltssm", 1100), ("async_fifo", 640),
    ("transaction_journey", 1100), ("testbench", 1100), ("reset_bug_waveform", 640),
]
BAR_NAMES = [("fault_recovery", 560), ("coverage", 560), ("synthesis_area", 640)]

html = SRC.read_text(encoding="utf-8")
style = re.search(r"<style>.*?</style>", html, re.S).group(0)
fonts = re.search(r'<link href="https://fonts[^>]+>', html).group(0)
defs = re.search(r'<svg width="0" height="0".*?</svg>', html, re.S).group(0)


def balanced(text, start, tag):
    """Return the element starting at text[start] with balanced <tag> nesting."""
    depth, i = 0, start
    pat = re.compile(rf"<{tag}\b|</{tag}>")
    for m in pat.finditer(text, start):
        depth += 1 if m.group(0) != f"</{tag}>" else -1
        if depth == 0:
            return text[start:m.end()]
    raise ValueError(tag)


svgs = [balanced(html, m.start(), "svg") for m in re.finditer(r'<svg viewBox="', html)]
svgs = [s for s in svgs if 'viewBox="0 0 24 24"' not in s]
bars = [balanced(html, m.start(), "div") for m in re.finditer(r'<div class="bars', html)]
assert len(svgs) == len(SVG_NAMES), len(svgs)
assert len(bars) == len(BAR_NAMES), len(bars)


def trim(img, pad=18):
    bg = Image.new(img.mode, img.size, (255, 255, 255))
    box = ImageChops.difference(img, bg).getbbox()
    img = img.crop(box)
    out = Image.new("RGB", (img.width + 2 * pad, img.height + 2 * pad), (255, 255, 255))
    out.paste(img, (pad, pad))
    return out


def render(snippet, width, path):
    page = (f"<!doctype html><html><head><meta charset='utf-8'>{fonts}{style}"
            f"<style>@page{{size:{width + 40}px 2400px;margin:0}}body{{background:#fff}}</style></head>"
            f"<body>{defs}<div style='width:{width}px;padding:20px'>{snippet}</div></body></html>")
    with tempfile.TemporaryDirectory() as td:
        h = pathlib.Path(td) / "fig.html"
        pdf = pathlib.Path(td) / "fig.pdf"
        h.write_text(page, encoding="utf-8")
        subprocess.run([EXE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=8000", f"--print-to-pdf={pdf}", h.as_uri()],
                       check=True, timeout=120, capture_output=True)
        doc = pymupdf.open(pdf)
        pix = doc[0].get_pixmap(dpi=144)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        doc.close()
    trim(img).save(path, optimize=True)
    print("wrote", path.relative_to(ROOT))


def pages(pdf, folder, dpi, fmt):
    folder.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    for i, p in enumerate(doc):
        out = folder / fmt.format(i + 1)
        Image.open(io.BytesIO(p.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB").save(out, optimize=True)
        print("wrote", out.relative_to(ROOT))


OUT.mkdir(parents=True, exist_ok=True)
for (name, w), s in zip(SVG_NAMES, svgs):
    render(s, w, OUT / f"{name}.png")
for (name, w), b in zip(BAR_NAMES, bars):
    render(b, w, OUT / f"{name}.png")
pages(ROOT / "docs" / "D2D-Link_Project_Report.pdf", OUT / "report", 72, "page-{:02d}.png")
pages(ROOT / "docs" / "D2D-Link_Explained.pdf", OUT / "explainer", 72, "page-{}.png")
