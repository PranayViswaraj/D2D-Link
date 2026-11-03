"""Generate docs/D2D-Link_Explained.pdf - an 8-page step-by-step explainer.
Measured numbers come from the project's log files (docs/results.md); parameter values from docs/spec.md.
Usage (Windows host, needs reportlab + Segoe UI fonts):
  python scripts/make_explainer_pdf.py docs/D2D-Link_Explained.pdf logs/coverage_merged.json
"""
import json
import math
import sys
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

OUT, COV = sys.argv[1], sys.argv[2]
W, H = A4
M = 40
CW = W - 2 * M          # content width
GAP = 18
COL = (CW - GAP) / 2    # half column

F = "C:/Windows/Fonts/"
for n, f in [("UI", "segoeui"), ("UI-B", "segoeuib"), ("UI-SB", "seguisb"), ("UI-L", "segoeuisl"),
             ("Mono", "consola"), ("Mono-B", "consolab"), ("Disp", "bahnschrift")]:
    pdfmetrics.registerFont(TTFont(n, F + f + ".ttf"))
registerFontFamily("UI", normal="UI", bold="UI-B", italic="UI", boldItalic="UI-B")

NAVY, NAVY2 = HexColor("#0B1736"), HexColor("#13244F")
INK, SUB, MUTE, LINE, BG = (HexColor(h) for h in ("#1E293B", "#475569", "#94A3B8", "#E2E8F0", "#F8FAFC"))
TEAL, TEAL_L = HexColor("#0D9488"), HexColor("#CCFBF1")
BLUE, BLUE_L = HexColor("#2563EB"), HexColor("#DBEAFE")
VIO, VIO_L = HexColor("#7C3AED"), HexColor("#EDE9FE")
AMB, AMB_L = HexColor("#D97706"), HexColor("#FEF3C7")
RED, RED_L = HexColor("#E11D48"), HexColor("#FFE4E6")
GRN, GRN_L = HexColor("#16A34A"), HexColor("#DCFCE7")
MINT = HexColor("#5EEAD4")

BODY = ParagraphStyle("body", fontName="UI", fontSize=9.4, leading=13.6, textColor=INK)
BODY_S = ParagraphStyle("bodys", parent=BODY, fontSize=8.4, leading=11.8)
BODY_C = ParagraphStyle("bodyc", parent=BODY_S, alignment=TA_CENTER)
CELL = ParagraphStyle("cell", fontName="UI", fontSize=7.9, leading=10.2, textColor=INK)
CELL_H = ParagraphStyle("cellh", parent=CELL, fontName="UI-B", textColor=white)
CELL_OK = ParagraphStyle("cellok", parent=CELL, fontName="UI-B", textColor=GRN)
CELL_M = ParagraphStyle("cellm", parent=CELL, fontName="Mono", fontSize=7.4)

c = canvas.Canvas(OUT, pagesize=A4)
c.setTitle("D2D-Link - Explained Step by Step")
c.setAuthor("Pranay")
c.setSubject("UCIe-inspired chiplet die-to-die link controller: design and verification")
TOTAL = 8


# ------------------------------------------------------------------ primitives
def para(t, x, y_top, w, style=BODY):
    p = Paragraph(t, style)
    _, h = p.wrap(w, 2000)
    p.drawOn(c, x, y_top - h)
    return y_top - h


def rrect(x, y, w, h, r=6, fill=None, stroke=None, lw=0.8, dash=None):
    c.saveState()
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(lw)
    if dash:
        c.setDash(*dash)
    c.roundRect(x, y, w, h, r, stroke=int(stroke is not None), fill=int(fill is not None))
    c.restoreState()


def text(x, y, s, font="UI", size=9, color=INK, anchor="l"):
    c.setFont(font, size)
    c.setFillColor(color)
    {"c": c.drawCentredString, "r": c.drawRightString}.get(anchor, c.drawString)(x, y, s)


def arrowhead(x2, y2, a, color, head=5):
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - head * math.cos(a - 0.4), y2 - head * math.sin(a - 0.4))
    p.lineTo(x2 - head * math.cos(a + 0.4), y2 - head * math.sin(a + 0.4))
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def arrow(x1, y1, x2, y2, color=SUB, lw=1.1, head=5, dash=None):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    if dash:
        c.setDash(*dash)
    c.line(x1, y1, x2, y2)
    c.setDash()
    arrowhead(x2, y2, math.atan2(y2 - y1, x2 - x1), color, head)
    c.restoreState()


def polyarrow(pts, color=SUB, lw=1.1, dash=None):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    if dash:
        c.setDash(*dash)
    p = c.beginPath()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    c.drawPath(p, stroke=1, fill=0)
    c.setDash()
    (xa, ya), (xb, yb) = pts[-2], pts[-1]
    arrowhead(xb, yb, math.atan2(yb - ya, xb - xa), color)
    c.restoreState()


def label_pill(x, y, s, col, size=6.8, bg=white):
    w = pdfmetrics.stringWidth(s, "UI-SB", size) + 8
    rrect(x - w / 2, y - 3.5, w, 11, 5, bg)
    text(x, y, s, "UI-SB", size, col, "c")


def block(x, y, w, h, title, sub=None, fill=BLUE_L, stroke=BLUE, tcol=None, tsize=8.6, scol=SUB):
    rrect(x, y, w, h, 5, fill, stroke)
    tcol = tcol or stroke
    if sub:
        text(x + w / 2, y + h / 2 + 2, title, "UI-B", tsize, tcol, "c")
        text(x + w / 2, y + h / 2 - 9, sub, "UI", 7, scol, "c")
    else:
        text(x + w / 2, y + h / 2 - 3, title, "UI-B", tsize, tcol, "c")


def section(x, y, s, color=TEAL):
    c.setFillColor(color)
    c.rect(x, y - 1, 3, 12, fill=1, stroke=0)
    text(x + 9, y, s, "UI-B", 11.5, NAVY)
    return y - 10


def chip(x, y, s, fill=TEAL_L, col=TEAL, size=7.6, pad=6):
    w = pdfmetrics.stringWidth(s, "UI-SB", size) + 2 * pad
    rrect(x, y, w, 15, 7.5, fill)
    text(x + pad, y + 4.5, s, "UI-SB", size, col)
    return w


def table(data, x, y_top, widths, head=NAVY, cell_styles=None):
    rows = []
    for i, r in enumerate(data):
        row = []
        for j, v in enumerate(r):
            st = CELL_H if i == 0 else (cell_styles or {}).get(j, CELL)
            if i > 0 and str(v) == "PASS":
                st = CELL_OK
            row.append(Paragraph(str(v), st))
        rows.append(row)
    t = Table(rows, colWidths=widths)
    ts = [("BACKGROUND", (0, 0), (-1, 0), head), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    ts += [("BACKGROUND", (0, i), (-1, i), BG) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(ts))
    _, h = t.wrap(sum(widths), 2000)
    t.drawOn(c, x, y_top - h)
    return y_top - h


def callout(x, y_top, w, title, body, fill=AMB_L, col=AMB, style=BODY_S):
    p = Paragraph(body, style)
    _, ph = p.wrap(w - 24, 2000)
    h = ph + 32
    rrect(x, y_top - h, w, h, 6, fill)
    c.setFillColor(col)
    c.rect(x, y_top - h, 3.5, h, fill=1, stroke=0)
    text(x + 13, y_top - 16, title, "UI-B", 9, col)
    p.drawOn(c, x + 13, y_top - 23 - ph)
    return y_top - h


def card(x, y_top, w, title, body, fill=BG, stroke=LINE, tcol=NAVY, size=7.9, minh=0):
    p = Paragraph(body, ParagraphStyle("cd", parent=BODY_S, fontSize=size, leading=size * 1.36))
    _, ph = p.wrap(w - 20, 2000)
    h = max(ph + 31, minh)
    rrect(x, y_top - h, w, h, 6, fill, stroke)
    text(x + 10, y_top - 16, title, "UI-B", 8.6, tcol)
    p.drawOn(c, x + 10, y_top - 24 - ph)
    return y_top - h


def page_frame(n, step, title, subtitle):
    c.setFillColor(NAVY)
    c.rect(0, H - 92, W, 92, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, H - 95, W, 3, fill=1, stroke=0)
    text(M, H - 34, step.upper(), "UI-SB", 8.5, MINT)
    text(M, H - 60, title, "Disp", 22, white)
    text(M, H - 79, subtitle, "UI-L", 10, HexColor("#CBD5E1"))
    for i in range(1, TOTAL + 1):
        cx = W - M - (TOTAL - i) * 15 - 4
        c.setFillColor(MINT if i == n else HexColor("#334155"))
        c.circle(cx, H - 34, 3.6 if i == n else 2.6, fill=1, stroke=0)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(M, 34, W - M, 34)
    text(M, 22, "D2D-Link  |  UCIe-inspired die-to-die link controller  |  explained step by step", "UI", 7.5, MUTE)
    text(W - M, 22, f"{n} / {TOTAL}", "UI-SB", 7.5, MUTE, "r")
    return H - 120


# ================================================================== PAGE 1 - cover
c.setFillColor(NAVY)
c.rect(0, H - 440, W, 440, fill=1, stroke=0)
for i, col in enumerate([TEAL, BLUE, VIO, AMB]):
    c.setFillColor(col)
    c.rect(M + i * 34, H - 120, 30, 6, fill=1, stroke=0)
text(M, H - 100, "PORTFOLIO PROJECT  |  RTL DESIGN + VERIFICATION", "UI-SB", 9, MINT)
text(M, H - 178, "D2D-Link", "Disp", 56, white)
text(M, H - 212, "A UCIe-inspired chiplet die-to-die link controller,", "UI-L", 16, HexColor("#E2E8F0"))
text(M, H - 232, "explained step by step.", "UI-L", 16, HexColor("#E2E8F0"))
para("<font color='#CBD5E1'>AXI4 traffic from Die A to Die B over a flit-based link with CRC-16, Go-Back-N retry, "
     "credit flow control on two virtual channels, link training, and three asynchronous clock domains. "
     "Synthesizable SystemVerilog, verified with open-source tools only.</font>",
     M, H - 252, 400, ParagraphStyle("cv", parent=BODY, fontSize=10, leading=15))
y0 = H - 392
dk = HexColor("#334155")
block(M, y0, 72, 40, "AXI host", fill=NAVY2, stroke=dk, tcol=white)
block(M + 98, y0, 124, 40, "Die A", "AXI slave + link layer", HexColor("#1E3A8A"), BLUE, white, scol=HexColor("#BFDBFE"))
block(M + 295, y0, 124, 40, "Die B", "link layer + AXI master", HexColor("#4C1D95"), VIO, white, scol=HexColor("#DDD6FE"))
block(M + 443, y0, 72, 40, "Memory", fill=NAVY2, stroke=dk, tcol=white)
arrow(M + 72, y0 + 20, M + 98, y0 + 20, MUTE)
arrow(M + 419, y0 + 20, M + 443, y0 + 20, MUTE)
arrow(M + 222, y0 + 28, M + 295, y0 + 28, MINT, 1.6)
arrow(M + 295, y0 + 12, M + 222, y0 + 12, MINT, 1.6)
text(M + 258, y0 + 46, "flits on 32-bit lanes", "UI", 7, MINT, "c")

stats = [("44 / 44", "regression jobs pass", GRN), ("5,108", "AXI transactions checked", BLUE),
         ("3,604", "faulted flits recovered", RED), ("100%", "functional coverage (233 bins)", TEAL),
         ("4", "unbounded formal proofs", VIO), ("0", "lint warnings", AMB)]
tw = (CW - 5 * 10) / 6
for i, (v, l, col) in enumerate(stats):
    x = M + i * (tw + 10)
    rrect(x, H - 530, tw, 72, 7, white, LINE)
    c.setFillColor(col)
    c.rect(x + 12, H - 462, tw - 24, 2.5, fill=1, stroke=0)
    text(x + tw / 2, H - 490, v, "Disp", 19, col, "c")
    para(l, x + 5, H - 499, tw - 10, ParagraphStyle("st", parent=BODY_C, fontSize=7.2, leading=9, textColor=SUB))

y = section(M, H - 568, "What this document walks through")
steps = [("1", "The big picture", "What a die-to-die link is, what D2D-Link does"),
         ("2", "The flit", "How data is packed, framed and CRC-protected"),
         ("3", "Reliability", "Go-Back-N retry, replay buffer, credits, virtual channels"),
         ("4", "Training and clocks", "Link state machine and safe clock crossings"),
         ("5", "A transaction's journey", "One AXI write followed hop by hop"),
         ("6", "Verification", "pyuvm testbench, fault injection, coverage, formal"),
         ("7", "Results and lessons", "The bug found, synthesis estimates, limitations"),
         ("8", "Design Q&A", "Common design questions, answered from the RTL")]
for i, (n, t, d) in enumerate(steps):
    col, row = i % 2, i // 2
    x = M + col * (COL + GAP)
    yy = y - 10 - row * 42
    c.setFillColor(TEAL if col == 0 else BLUE)
    c.circle(x + 11, yy - 12, 10.5, fill=1, stroke=0)
    text(x + 11, yy - 15.6, n, "UI-B", 10, white, "c")
    text(x + 29, yy - 9, t, "UI-B", 10, NAVY)
    text(x + 29, yy - 22, d, "UI", 8, SUB)
c.setStrokeColor(LINE)
c.line(M, 52, W - M, 52)
text(M, 38, "Tools: Verilator 5.020  |  cocotb 1.9.2  |  pyuvm 3.0.0  |  cocotb-coverage 1.2.0  |  SymbiYosys + z3 / ABC PDR  |  "
     "Yosys 0.33  |  Verible  |  SKY130 HD", "UI", 7.5, MUTE)
text(M, 24, "Author: Pranay", "UI-SB", 8, SUB)
text(W - M, 24, "Measured numbers come from log files in the repository (docs/results.md).", "UI", 7.5, MUTE, "r")
c.showPage()

# ================================================================== PAGE 2 - big picture
y = page_frame(2, "Step 1", "The big picture", "Why die-to-die links exist, and what this controller does")
y = para("Modern processors are increasingly built from <b>chiplets</b>: several smaller dies in one package "
         "instead of one huge die. The dies still have to talk to each other as if they were one chip. A "
         "<b>die-to-die (D2D) link controller</b> does that job. It takes on-chip bus traffic on one die, packs it "
         "into small fixed-size packets called <b>flits</b>, sends them across a few wires, and rebuilds the bus "
         "traffic on the other die. Industry standards such as UCIe define this. D2D-Link is a smaller design built "
         "on the same ideas, for a host on Die A that reads and writes a memory on Die B.", M, y, CW)
y = section(M, y - 16, "System architecture")
top = y - 6
dh = 232
rrect(M, top - dh, CW, dh, 8, BG, LINE)
rrect(M + 54, top - dh + 34, 196, dh - 52, 8, None, BLUE, 1.2)
rrect(M + 265, top - dh + 34, 196, dh - 52, 8, None, VIO, 1.2)
text(M + 62, top - 30, "DIE A  (die_a_top)", "UI-B", 8.5, BLUE)
text(M + 273, top - 30, "DIE B  (die_b_top)", "UI-B", 8.5, VIO)
block(M + 8, top - 132, 40, 40, "Host", fill=white, stroke=MUTE, tcol=INK, tsize=8)
block(W - M - 48, top - 132, 40, 40, "Mem", fill=white, stroke=MUTE, tcol=INK, tsize=8)
block(M + 62, top - 82, 80, 36, "AXI slave", "adapter", BLUE_L, BLUE)
block(M + 62, top - 180, 80, 36, "APB CSR", "registers", BLUE_L, BLUE)
block(M + 164, top - 135, 78, 54, "Link layer", "TX + RX", TEAL_L, TEAL)
block(M + 273, top - 135, 78, 54, "Link layer", "TX + RX", TEAL_L, TEAL)
block(M + 373, top - 82, 80, 36, "AXI master", "adapter", VIO_L, VIO)
block(M + 373, top - 180, 80, 36, "APB CSR", "registers", VIO_L, VIO)
for fx, fy in [(M + 146, top - 74), (M + 146, top - 160), (M + 355, top - 74), (M + 355, top - 160)]:
    rrect(fx, fy, 14, 22, 2, AMB_L, AMB)
    c.setStrokeColor(AMB)
    for k in range(1, 4):
        c.line(fx + 2, fy + k * 5.5, fx + 12, fy + k * 5.5)
arrow(M + 48, top - 112, M + 62, top - 70)
arrow(W - M - 62 - 0, top - 70, W - M - 48, top - 112)
arrow(M + 142, top - 64, M + 178, top - 81)
arrow(M + 142, top - 162, M + 178, top - 135)
arrow(M + 338, top - 81, M + 373, top - 64)
arrow(M + 338, top - 135, M + 373, top - 162)
arrow(M + 242, top - 98, M + 273, top - 98, TEAL, 1.8)
arrow(M + 273, top - 120, M + 242, top - 120, TEAL, 1.8)
text(M + 257, top - 92, "a2b", "UI-SB", 6.5, TEAL, "c")
text(M + 257, top - 131, "b2a", "UI-SB", 6.5, TEAL, "c")
for i, (lab, col) in enumerate([("clk_axi_a domain", BLUE), ("clk_link domain", TEAL), ("clk_axi_b domain", VIO),
                                 ("async FIFO: the only clock crossing", AMB)]):
    lx = M + 14 + i * 122
    c.setFillColor(col)
    c.rect(lx, top - dh + 13, 8, 8, fill=1, stroke=0)
    text(lx + 12, top - dh + 14, lab, "UI", 7, SUB)
y = top - dh - 22

ys = section(M, y, "Three layers, bottom to top")
layers = [("Protocol layer", "AXI adapters turn bus channels (AW, W, B, AR, R) into flit bodies and back again.", BLUE_L, BLUE),
          ("Link layer", "Adds sequence numbers, CRC, retry, credits and training. Delivers flits in order, with no loss.", TEAL_L, TEAL),
          ("Physical lane model", "A 32-bit lane, 4 beats per flit. The testbench injects bit flips and drops here.", AMB_L, AMB)]
ly = ys - 4
for t, d, f, s in layers:
    hh = 46
    rrect(M, ly - hh, COL, hh, 6, f)
    c.setFillColor(s)
    c.rect(M, ly - hh, 3.5, hh, fill=1, stroke=0)
    text(M + 12, ly - 15, t, "UI-B", 9, s)
    para(d, M + 12, ly - 20, COL - 22, ParagraphStyle("lx", parent=BODY_S, fontSize=7.9, leading=10.2))
    ly -= hh + 6
x2 = M + COL + GAP
yr = section(x2, y, "What the design supports")
specs = [("AXI4 subset", "64-bit data, 32-bit addr, 4-bit ID"), ("Bursts", "INCR, 1 to 16 beats, full WSTRB"),
         ("Outstanding", "4 writes + 4 reads at Die A"), ("Ordering", "strictly in order (documented)"),
         ("Flit", "128 bits, CRC-16/CCITT"), ("Retry", "Go-Back-N, 16-entry replay buffer"),
         ("Flow control", "credits on 2 virtual channels"), ("Clocks", "3 asynchronous domains"),
         ("Control", "APB3 CSRs + interrupts per die")]
yy = yr - 2
for k, v in specs:
    text(x2 + 4, yy - 11, k, "UI-SB", 8.2, NAVY)
    text(x2 + 92, yy - 11, v, "UI", 8.2, SUB)
    c.setStrokeColor(LINE)
    c.line(x2, yy - 15.5, x2 + COL, yy - 15.5)
    yy -= 16.2
y = min(ly, yy) - 16
y = section(M, y, "Glossary: eight words you will meet on every page", AMB)
terms = [("Flit", "fixed 128-bit packet, the unit the link moves"), ("CRC", "16-bit checksum that detects corrupted flits"),
         ("SEQ / ACK", "flit numbering, and \"I got everything before N\""), ("NAK", "\"something was bad, resend from N\""),
         ("Credit", "permission to use one free slot in the receiver"), ("Virtual channel", "independent lane of credits (REQ, RSP)"),
         ("CDC", "moving data safely between unrelated clocks"), ("Gray code", "counter encoding where one bit changes per step")]
gw = (CW - 3 * 8) / 4
for i, (k, v) in enumerate(terms):
    col, row = i % 4, i // 4
    x = M + col * (gw + 8)
    yy = y - 6 - row * 50
    rrect(x, yy - 44, gw, 44, 6, white, LINE)
    text(x + 9, yy - 15, k, "UI-B", 8.6, AMB)
    para(v, x + 9, yy - 20, gw - 16, ParagraphStyle("g", parent=BODY_S, fontSize=7.4, leading=9.4, textColor=SUB))
c.showPage()

# ================================================================== PAGE 3 - flit
y = page_frame(3, "Step 2", "The flit", "The 128-bit packet that carries everything across the link")
y = para("Every piece of information crossing the link travels in a <b>flit</b> (flow-control unit), a fixed 128-bit "
         "packet. A fixed size keeps the hardware simple: the receiver always knows where a flit ends, and the CRC "
         "always covers the same bits. Each flit has a header, a 72-bit payload and a 16-bit CRC.", M, y, CW)
y = section(M, y - 16, "Bit layout")
fields = [("TYPE", 4, NAVY, "TYP"), ("SEQ", 8, BLUE, "SEQ"), ("ACK_SEQ", 8, TEAL, "ACK"), ("CRED_REQ", 8, GRN, "CRQ"),
          ("CRED_RSP", 8, GRN, "CRS"), ("FLAGS", 4, SUB, "F"), ("PAYLOAD", 72, VIO, "PAYLOAD  (72 bits)"),
          ("CRC", 16, RED, "CRC-16")]
by = y - 50
sc = CW / 128
xx, bit = M, 127
for name, n, col, short in fields:
    ww = n * sc
    c.setFillColor(col)
    c.rect(xx, by, ww - 1.2, 30, fill=1, stroke=0)
    text(xx + ww / 2 - 0.6, by + 11, short, "UI-B", 7.4 if ww > 24 else 6.4, white, "c")
    text(xx + 1, by + 34, str(bit), "Mono", 6.2, MUTE)
    bit -= n
    xx += ww
text(M + CW - 5, by + 34, "0", "Mono", 6.2, MUTE)
desc = [("TYPE", NAVY, "which kind of flit (table below)"), ("SEQ", BLUE, "sequence number, used by retry"),
        ("ACK_SEQ", TEAL, "next SEQ expected from the other side"), ("CRED_*", GRN, "running count of freed receive slots, per channel"),
        ("FLAGS", SUB, "LAST beat of a burst, or LOCKED in training"), ("CRC", RED, "error check over bits 127..16")]
yy = by - 12
for i, (k, col, v) in enumerate(desc):
    x = M + (i % 2) * (COL + GAP)
    ry = yy - (i // 2) * 14
    c.setFillColor(col)
    c.rect(x, ry - 1, 7, 7, fill=1, stroke=0)
    text(x + 11, ry, k, "Mono-B", 7.6, NAVY)
    text(x + 62, ry, v, "UI", 7.8, SUB)
y = yy - 3 * 14 - 8

yl = section(M, y, "Nine flit types")
data = [["Code", "Type", "Retried", "Carries"],
        ["1", "REQ_HDR", "yes", "AW or AR: address, ID, length"],
        ["2", "REQ_DATA", "yes", "W beat: 64-bit data + strobes"],
        ["3", "RSP_HDR", "yes", "B response: ID, resp"],
        ["4", "RSP_DATA", "yes", "R beat: 64-bit data, ID, resp"],
        ["0, 5, 7", "IDLE, ACK, CREDIT", "no", "filler; still carries ACK + credits"],
        ["6", "NAK", "no", "resend from ACK_SEQ"],
        ["8", "TRAIN", "no", "fixed pattern + LOCKED bit"]]
yl = table(data, M, yl - 2, [38, 84, 40, COL - 162])
x2 = M + COL + GAP
yr = section(x2, y, "Four beats on a 32-bit lane")
wy = yr - 22
c.setStrokeColor(AMB)
c.setLineWidth(1.4)
bx0 = x2 + 30
c.line(bx0, wy - 12, bx0, wy)
c.line(bx0, wy, bx0 + 52, wy)
c.line(bx0 + 52, wy, bx0 + 52, wy - 12)
c.line(bx0 + 52, wy - 12, bx0 + 4 * 54, wy - 12)
text(x2, wy - 9, "sof", "Mono-B", 7.4, AMB)
for i in range(4):
    col = [BLUE, TEAL, VIO, RED][i]
    rrect(bx0 + i * 54, wy - 58, 50, 36, 4, [BLUE_L, TEAL_L, VIO_L, RED_L][i], col)
    text(bx0 + i * 54 + 25, wy - 37, f"beat {i}", "UI-B", 8, col, "c")
    text(bx0 + i * 54 + 25, wy - 49, ["127..96", "95..64", "63..32", "31..0"][i], "Mono", 6.5, SUB, "c")
text(x2, wy - 43, "data", "Mono-B", 7.4, SUB)
yr = para("One beat per <b>clk_link</b> cycle, MSB first. <font name='Mono'>sof</font> marks beat 0 so the receiver can "
          "realign; a truncated flit counts as an error and triggers a NAK. The link always sends something: when "
          "there is no data it sends IDLE, ACK or CREDIT flits, which keeps ACKs and credits flowing.",
          x2, wy - 68, COL, BODY_S)
y = min(yl, yr) - 16
y = section(M, y, "What the 72-bit payload holds")
data = [["Flit type", "Payload fields (bit 87 down to 16)", "Used for"],
        ["REQ_HDR", "is_write | ID[4] | address[32] | len[4] | size[3] | burst[2]", "one AXI AW or AR"],
        ["REQ_DATA", "wdata[64] | wstrb[8]   (FLAGS.LAST = last beat)", "one AXI W beat"],
        ["RSP_HDR", "bid[4] | bresp[2]", "one AXI B response"],
        ["RSP_DATA", "rdata[64] | rid[4] | rresp[2]   (FLAGS.LAST = RLAST)", "one AXI R beat"],
        ["TRAIN", "fixed 72-bit pattern 0xD2D2_A5A5_5A5A_C3C3_3C", "link training"]]
y = table(data, M, y - 2, [70, CW - 180, 110], cell_styles={1: CELL_M})
y -= 12
callout(M, y, CW, "CRC-16: catching corrupted flits",
        "The transmitter runs the 112 header + payload bits through a <b>CRC-16/CCITT</b> (polynomial 0x1021, start "
        "value 0xFFFF) and appends the 16-bit result. The receiver recomputes it; a mismatch means the flit was damaged, "
        "so it is dropped and a NAK is sent. CRC-16 is guaranteed to catch any 1, 2 or 3 flipped bits and any burst of "
        "up to 16 bits. In hardware it is one combinational XOR tree (<font name='Mono'>rtl/common/crc16.sv</font>), "
        "checked against a Python model on 1,004 random and corner-case vectors.", TEAL_L, TEAL)
c.showPage()

# ================================================================== PAGE 4 - reliability
y = page_frame(4, "Step 3", "Reliability: retry and credits",
               "How the link delivers every flit in order, without overflowing the receiver")
yl = section(M, y, "Go-Back-N retry, in action")
sx1, sx2 = M + 26, M + COL - 86
st = yl - 22
text(sx1, st + 7, "Transmitter", "UI-B", 8.5, BLUE, "c")
text(sx2, st + 7, "Receiver", "UI-B", 8.5, VIO, "c")
sb = st - 262
c.setStrokeColor(MUTE)
c.setDash(2, 2)
c.line(sx1, st, sx1, sb)
c.line(sx2, st, sx2, sb)
c.setDash()
yy = st - 18
seqd = [(5, "accept", BLUE, GRN), (6, "accept", BLUE, GRN), (7, "CRC error", RED, RED), (8, "drop (out of order)", MUTE, SUB)]
for seq, note, col, ncol in seqd:
    arrow(sx1, yy, sx2, yy - 16, col, 1.2)
    text(sx1 + 6, yy + 3, f"SEQ {seq}", "Mono-B", 7.2, col)
    text(sx2 + 6, yy - 19, note, "UI-SB", 6.8, ncol)
    if seq == 7:
        text((sx1 + sx2) / 2, yy - 12, "X", "UI-B", 11, RED, "c")
    yy -= 32
arrow(sx2, yy, sx1, yy - 16, AMB, 1.4)
text(sx2 - 6, yy + 3, "NAK  (ACK_SEQ = 7)", "Mono-B", 7.2, AMB, "r")
text(sx1 + 14, yy - 27, "rewind: rd_seq = 7", "UI-SB", 6.8, AMB)
yy -= 44
for seq in (7, 8):
    arrow(sx1, yy, sx2, yy - 16, GRN, 1.2)
    text(sx1 + 6, yy + 3, f"SEQ {seq}  (replay)", "Mono-B", 7.2, GRN)
    text(sx2 + 6, yy - 19, "accept", "UI-SB", 6.8, GRN)
    yy -= 32
yl = para("Every data flit gets a <b>sequence number</b>, and a copy stays in the <b>replay buffer</b> until it is "
          "acknowledged. When the receiver sees a bad or out-of-order flit it sends one <b>NAK</b>, and the transmitter "
          "<i>goes back</i> and resends everything from that point. If a flit vanishes and nothing follows it, a "
          "<b>replay timeout</b> triggers the same rewind.", M, sb - 8, COL, BODY_S)

x2 = M + COL + GAP
yr = section(x2, y, "The replay buffer: three pointers")
slots = 12
sw = COL / slots
ry = yr - 54
for i in range(slots):
    f = GRN_L if i < 3 else AMB_L if i < 7 else BLUE_L if i < 9 else white
    rrect(x2 + i * sw, ry, sw - 2, 24, 2, f, LINE)
    text(x2 + i * sw + sw / 2 - 1, ry + 9, str(20 + i), "Mono", 6.6, SUB, "c")
for lab, i, col in (("ack_seq", 3, GRN), ("rd_seq", 7, AMB), ("wr_seq", 9, BLUE)):
    px = x2 + i * sw + 1
    arrow(px, ry + 40, px, ry + 26, col, 1.2)
    text(px, ry + 43, lab, "Mono-B", 6.8, col, "c")
for i, (f, l) in enumerate([(GRN_L, "acknowledged (free)"), (AMB_L, "sent, awaiting ACK"), (BLUE_L, "queued, not sent")]):
    rrect(x2 + i * 84, ry - 17, 9, 9, 2, f, LINE)
    text(x2 + i * 84 + 13, ry - 15, l, "UI", 6.6, SUB)
yr = para("The rule is <font name='Mono'>ack &le; rd &le; wr</font> and <font name='Mono'>wr - ack &le; 16</font>. "
          "There are 256 sequence numbers and the window is 16, less than half, so the receiver can always tell a "
          "<b>duplicate</b> (drop it) from a <b>gap</b> (NAK it). This invariant is <b>formally proven</b>.",
          x2, ry - 28, COL, BODY_S)
yr = section(x2, yr - 16, "Credits: never overflow the receiver", GRN)
yr = para("A <b>credit</b> is one free slot in the receiver's buffer. The transmitter may only send while it holds a "
          "credit; the receiver hands credits back as its buffer drains.", x2, yr - 2, COL, BODY_S)
cy = yr - 66
block(x2, cy, 64, 44, "TX", "credits 3/16", BLUE_L, BLUE)
block(x2 + COL - 74, cy, 74, 44, "RX buffer", "async FIFO", VIO_L, VIO)
arrow(x2 + 64, cy + 32, x2 + COL - 74, cy + 32, BLUE, 1.2)
arrow(x2 + COL - 74, cy + 12, x2 + 64, cy + 12, GRN, 1.2)
label_pill(x2 + COL / 2 - 5, cy + 37, "data flit: spends 1", BLUE)
label_pill(x2 + COL / 2 - 5, cy + 17, "freed count returns", GRN)
y = min(yl, cy) - 18

y = section(M, y, "Three design decisions worth remembering", AMB)
cards = [("Cumulative, not incremental",
          "ACK and credit fields carry <b>running totals</b> (mod 256). If the flit carrying them is lost, the next good "
          "flit has the up-to-date total, so a credit or ACK can never leak away."),
         ("Credits are spent once",
          "A credit is consumed when a flit enters the replay buffer, not each time it is sent. Replays never spend "
          "credits again, so an in-order flit always finds a free slot (asserted in RTL)."),
         ("Two virtual channels",
          "Requests and responses have <b>separate credits</b>. A jammed request path can never block the responses "
          "that would clear it, which removes protocol deadlock.")]
cw3 = (CW - 20) / 3
for i, (t, d) in enumerate(cards):
    card(M + i * (cw3 + 10), y - 2, cw3, t, d, minh=92)
y -= 108
y = section(M, y, "What triggers a replay, and how often it happened in the final regression")
data = [["Trigger", "Detected by", "Recovery", "Count (44 runs)"],
        ["Corrupted flit", "CRC mismatch at the receiver", "NAK, then Go-Back-N replay", "350 NAKs sent"],
        ["Lost flit followed by more data", "SEQ gap at the next flit", "NAK, then replay", "(included above)"],
        ["Lost last flit, lost NAK or ACKs", "replay timer expires", "replay from oldest unACKed", "62 timeouts"],
        ["Error burst above threshold", "error-window counter", "retrain, then replay", "26 retrains"],
        ["All of the above", "-", "flits actually resent", "353 replays"]]
table(data, M, y - 2, [130, 140, 130, CW - 400])
c.showPage()

# ================================================================== PAGE 5 - training + CDC
y = page_frame(5, "Step 4", "Link training and clock domains",
               "Bringing the link up safely, and moving data between unrelated clocks")
y = section(M, y, "The link training state machine")
y = para("Before any data flows, both dies must agree the link works. Each side sends <b>TRAIN</b> flits; after 8 good "
         "ones in a row it is <b>locked</b> and says so in its own TRAIN flits. When both sides are locked, the link goes "
         "<b>ACTIVE</b>. Too many errors send it back to <b>RETRAIN</b>; too many failed attempts end in <b>FAILED</b>.",
         M, y - 2, CW)
fy = y - 150
sw_, sh_ = 92, 38
pos = {"RESET": (M + 4, fy + 84), "TRAIN": (M + 144, fy + 84), "ACTIVE": (M + 284, fy + 84),
       "RETRAIN": (M + 284, fy + 4), "FAILED": (M + 419, fy + 44)}
cols = {"RESET": (BG, SUB), "TRAIN": (AMB_L, AMB), "ACTIVE": (GRN_L, GRN), "RETRAIN": (AMB_L, AMB), "FAILED": (RED_L, RED)}
for s, (px, py) in pos.items():
    f, sc_ = cols[s]
    rrect(px, py, sw_, sh_, 18, f, sc_, 1.4)
    text(px + sw_ / 2, py + 15, s, "UI-B", 9.5, sc_, "c")
P = lambda s, dx, dy: (pos[s][0] + dx, pos[s][1] + dy)
arrow(*P("RESET", sw_, 19), *P("TRAIN", 0, 19), SUB)
label_pill(M + 120, fy + 112, "enable", SUB, bg=BG)
arrow(*P("TRAIN", sw_, 19), *P("ACTIVE", 0, 19), GRN, 1.3)
label_pill(M + 260, fy + 113, "both locked", GRN, bg=BG)
arrow(*P("ACTIVE", 30, 0), *P("RETRAIN", 30, sh_), AMB, 1.3)
arrow(*P("RETRAIN", 62, sh_), *P("ACTIVE", 62, 0), GRN, 1.3)
text(M + 306, fy + 66, "errors /", "UI", 6.6, AMB, "r")
text(M + 306, fy + 58, "forced", "UI", 6.6, AMB, "r")
text(M + 352, fy + 62, "re-locked", "UI", 6.6, GRN)
arrow(*P("ACTIVE", sw_, 19), *P("FAILED", 20, sh_), RED, 1.2)
arrow(*P("RETRAIN", sw_, 19), *P("FAILED", 20, 0), RED, 1.2)
label_pill(M + 442, fy + 18, "retry budget used up", RED, bg=BG)
polyarrow([P("FAILED", 70, 0), (pos["FAILED"][0] + 70, fy - 14), (M + 50, fy - 14), P("RESET", 46, 0)], RED, 1.0, (3, 2))
label_pill(M + 170, fy - 14, "software toggles CTRL.ENABLE: FAILED -> RESET -> TRAIN", RED, bg=white)
y = fy - 34
y = callout(M, y, CW, "No data is lost across a retrain",
            "Retraining never touches the replay buffer, sequence numbers, credits or receive FIFOs. On return to ACTIVE "
            "the transmitter replays everything still unacknowledged and the receiver drops duplicates by sequence "
            "number. A TRAIN flit with LOCKED=1 arriving while ACTIVE is ignored: without that rule the two dies could "
            "keep knocking each other back into retraining forever.", GRN_L, GRN)
y -= 8
data = [["Knob (default)", "Meaning", "Knob (default)", "Meaning"],
        ["ERR_THRESH = 8", "retrain if > 8 bad flits in a window", "TRAIN_GOOD = 8", "good TRAIN flits needed to lock"],
        ["ERR_WINDOW = 256", "window length, in received flits", "TRAIN_TIMEOUT = 1024", "cycles per training attempt"],
        ["MAX_RETRAIN = 4", "attempts before FAILED", "STABLE_CYCLES = 2048", "ACTIVE time that resets the attempt count"]]
y = table(data, M, y, [92, CW / 2 - 92, 102, CW / 2 - 102])
y -= 16
yl = section(M, y, "Clock-domain crossing (CDC)")
yl = para("The two AXI sides and the link run on <b>three unrelated clocks</b>. Sampling a changing multi-bit value from "
          "another clock can capture a half-updated number. The rule here is strict: <b>every crossing is an async FIFO "
          "with gray-coded pointers</b>, and nothing else crosses.", M, yl - 2, COL, BODY_S)
yl = section(M, yl - 14, "Why gray code?", AMB)
gy = yl - 4
data = [["Step", "Binary", "Gray", "bits that change"],
        ["3 to 4", "011 to 100", "010 to 110", "binary 3, gray 1"],
        ["7 to 0", "111 to 000", "100 to 000", "binary 3, gray 1"]]
gy = table(data, M, gy, [44, 70, 70, COL - 184], head=AMB, cell_styles={1: CELL_M, 2: CELL_M})
para("If the reading clock samples mid-change, a gray pointer is always either the old or the new value, never a "
     "random third one. The FIFO was <b>formally proven</b> with two unconstrained clocks.", M, gy - 6, COL, BODY_S)
x2 = M + COL + GAP
yr = section(x2, y, "The 8 crossings")
data = [["#", "Die", "Direction", "Carries"],
        ["1", "A", "axi_a to link", "requests (AW / W / AR flits)"],
        ["2", "A", "link to axi_a", "responses; RSP credit buffer"],
        ["3, 7", "A, B", "axi to link", "CSR config messages"],
        ["4, 8", "A, B", "link to axi", "status + counter snapshots"],
        ["5", "B", "link to axi_b", "requests; REQ credit buffer"],
        ["6", "B", "axi_b to link", "responses (B / R flits)"]]
yr = table(data, x2, yr - 2, [28, 30, 70, COL - 128])
para("<b>Counters</b> cross as one coherent snapshot through a FIFO, never bit by bit. <b>Credit return</b> reuses the "
     "receive FIFO's already-synchronized read pointer, so it needs no extra crossing; it lags by 2 to 3 cycles, so "
     "credits come back late, never early.", x2, yr - 6, COL, BODY_S)
c.showPage()

# ================================================================== PAGE 6 - journey
y = page_frame(6, "Step 5", "A transaction's journey", "Following one AXI write burst from the host to memory and back")
steps6 = [
    ("Host", BLUE, "The host drives <b>AW</b> (address, ID, length) on Die A. The slave adapter accepts it only if fewer than "
     "4 writes are outstanding, then accepts each <b>W</b> beat."),
    ("Pack", BLUE, "The adapter turns AW into one <b>REQ_HDR</b> flit body and each W beat into a <b>REQ_DATA</b> body "
     "(64-bit data + 8 strobe bits), and pushes them into the request async FIFO."),
    ("Cross", AMB, "The bodies cross from <font name='Mono'>clk_axi_a</font> into <font name='Mono'>clk_link</font> through "
     "the gray-pointer FIFO."),
    ("Enqueue", TEAL, "If a REQ credit is available and the replay buffer has room, the body gets the next <b>SEQ</b>, is "
     "stored in the replay buffer, and one credit is spent."),
    ("Send", TEAL, "flit_tx adds SEQ, the current ACK and credit counts, computes the <b>CRC</b>, and sends the 128 bits as "
     "4 beats on the a2b lane."),
    ("Check", VIO, "flit_rx on Die B rebuilds the flit and checks CRC and SEQ. In order: accept it into the REQ receive FIFO. "
     "Bad or gap: NAK. Duplicate: drop."),
    ("Execute", VIO, "Die B's master adapter pops the header, drives <b>AW</b>, then the <b>W</b> beats to memory, and waits "
     "for the <b>B</b> response. One transaction at a time, in order."),
    ("Respond", VIO, "The B response becomes an <b>RSP_HDR</b> flit and travels back on the b2a lane on the RSP virtual "
     "channel, with its own credits."),
    ("ACK", GRN, "Every flit Die B sends carries ACK_SEQ. When Die A sees it, acknowledged entries leave the replay buffer. "
     "As FIFOs drain, the freed-slot counts return credits."),
    ("Done", GRN, "Die A pops the RSP_HDR and drives <b>B</b> to the host; the write retires. Reads work the same way, with "
     "R beats returning as RSP_DATA flits."),
]
yy = y + 2
lx = M + 12
for i, (t, col, d) in enumerate(steps6):
    p = Paragraph(d, ParagraphStyle("j", parent=BODY_S, fontSize=8.3, leading=11.2))
    _, ph = p.wrap(CW - 96, 300)
    hh = max(ph, 22) + 9
    if i < len(steps6) - 1:
        c.setStrokeColor(LINE)
        c.setLineWidth(2)
        c.line(lx, yy - 12, lx, yy - hh - 10)
    c.setFillColor(col)
    c.circle(lx, yy - 12, 10.5, fill=1, stroke=0)
    text(lx, yy - 15.6, str(i + 1), "UI-B", 9.5, white, "c")
    text(lx + 18, yy - 15, t, "UI-B", 9.5, col)
    p.drawOn(c, M + 92, yy - 6 - ph)
    yy -= hh + 5
y = yy - 8
yc = callout(M, y, COL, "If step 5 goes wrong",
             "A <b>corrupted</b> flit fails the CRC at step 6 and Die B sends a NAK; Die A rewinds and resends from that "
             "flit. A <b>dropped</b> flit shows up as a SEQ gap at the next flit (NAK), or, if nothing follows it, as a "
             "<b>replay timeout</b> on Die A. Either way the host just sees a slightly later B response.", RED_L, RED)
yd = callout(M + COL + GAP, y, COL, "Why one transaction at a time at Die B?",
             "Strict ordering makes every response predictable. The scoreboard can compute the exact expected read data "
             "and catch any reordering. The cost is throughput, which is documented as a limitation; per-ID "
             "reordering would be the next feature.", BLUE_L, BLUE)
y = min(yc, yd) - 16
y = section(M, y, "Control and status registers (APB3, one block per die)")
data = [["Offset", "Register", "What it does", "Offset", "Register", "What it does"],
        ["0x00", "CTRL", "ENABLE, FORCE_RETRAIN (pulse)", "0x1C", "ERR_CFG", "retrain threshold, retry budget"],
        ["0x04", "STATUS", "link state, LINK_UP", "0x20", "ERR_WINDOW", "error window (flits)"],
        ["0x08-18", "5 counters", "CRC errors, NAKs, replays, timeouts, retrains", "0x24 / 28", "IRQ_EN / STATUS",
         "link-down, retrain, failed, CRC (W1C)"],
        ["0x2C", "ID", "constant 0xD2D10001", "other", "-", "PSLVERR error response"]]
table(data, M, y - 2, [42, 56, 150, 44, 74, CW - 366])
c.showPage()

# ================================================================== PAGE 7 - verification
y = page_frame(7, "Step 6", "Verification", "Spec first, block tests, a UVM-style system testbench, fault injection and formal proofs")
flow = [("Spec", "4 docs"), ("Unit tests", "9 cases"), ("System tests", "14 tests"), ("Regression", "44 jobs"),
        ("Formal", "10 tasks"), ("Lint", "0 warnings"), ("Synthesis", "12 blocks")]
fw = (CW - 6 * 12) / 7
for i, (t, s) in enumerate(flow):
    x = M + i * (fw + 12)
    rrect(x, y - 38, fw, 38, 6, NAVY if i != 3 else TEAL)
    text(x + fw / 2, y - 16, t, "UI-B", 8.2, white, "c")
    text(x + fw / 2, y - 29, s, "UI", 7, MINT if i != 3 else white, "c")
    if i < 6:
        arrow(x + fw + 1, y - 19, x + fw + 11, y - 19, MUTE, 1)
y -= 56
yl = section(M, y, "The pyuvm testbench")
ty = yl - 160
rrect(M, ty, COL, 154, 8, BG, LINE)
text(M + 10, ty + 140, "D2dEnv", "UI-B", 8.5, NAVY)
bw2 = (COL - 30) / 2
block(M + 10, ty + 96, bw2, 34, "AXI master agent", "Die A host", BLUE_L, BLUE, tsize=7.8)
block(M + 20 + bw2, ty + 96, bw2, 34, "AXI memory agent", "Die B, reactive", VIO_L, VIO, tsize=7.8)
block(M + 10, ty + 54, bw2, 34, "Lane fault agents x2", "flips, bursts, drops", RED_L, RED, tsize=7.8)
block(M + 20 + bw2, ty + 54, bw2, 34, "APB agents x2", "CSR access", AMB_L, AMB, tsize=7.8)
block(M + 10, ty + 10, bw2, 36, "Scoreboard", "reference memory", GRN_L, GRN, tsize=7.8)
block(M + 20 + bw2, ty + 10, bw2, 36, "Coverage", "cocotb-coverage", TEAL_L, TEAL, tsize=7.8)
yl = para("The scoreboard keeps an exact <b>reference memory</b>. Because execution is strictly ordered, it predicts "
          "every response and read value, and checks that each request reaches Die B exactly once, in order. That "
          "catches <b>loss, duplication, reordering and corruption</b> under any fault.", M, ty - 8, COL, BODY_S)
x2 = M + COL + GAP
yr = section(x2, y, "14 seeded system tests")
tests = ["smoke", "random_rw", "max_burst", "outstanding_stress", "credit_starvation", "backpressure_random",
         "crc_error_retry", "flit_drop_timeout", "error_storm_retrain", "link_fail_and_recover", "csr_access",
         "ltssm_arcs", "clock_ratio_sweep", "reset_during_traffic"]
cx, cy_ = x2, yr - 20
for t in tests:
    wch = pdfmetrics.stringWidth(t, "UI-SB", 7.4) + 12
    if cx + wch > x2 + COL:
        cx, cy_ = x2, cy_ - 20
    fault = t in ("crc_error_retry", "flit_drop_timeout", "error_storm_retrain", "link_fail_and_recover", "reset_during_traffic")
    chip(cx, cy_, t, RED_L if fault else TEAL_L, RED if fault else TEAL, 7.4)
    cx += wch + 5
yr = para("<font color='#E11D48'><b>Red</b></font> = fault or reset stress. Every test takes a seed; the regression runs "
          "all tests over several seeds on all CPU cores under a 15-minute cap and writes JUnit XML.",
          x2, cy_ - 8, COL, BODY_S)
yr = section(x2, yr - 14, "Final regression (from logs)")
stats7 = [("44/44", "jobs pass", GRN), ("5,108", "transactions", BLUE), ("3,604", "faults injected", RED),
          ("350", "NAKs", AMB), ("353", "replays", TEAL), ("62", "timeouts", VIO)]
tw = (COL - 10) / 3
for i, (v, l, col) in enumerate(stats7):
    x = x2 + (i % 3) * (tw + 5)
    yy = yr - 2 - (i // 3) * 46
    rrect(x, yy - 40, tw, 40, 5, white, LINE)
    text(x + tw / 2, yy - 20, v, "Disp", 14, col, "c")
    text(x + tw / 2, yy - 32, l, "UI", 7, SUB, "c")
yr -= 2 + 2 * 46
y = min(yl, yr) - 16
y = section(M, y, "Formal proofs (SymbiYosys, small configuration)", VIO)
data = [["Job", "Method", "What is proven", "Result"],
        ["Async FIFO", "ABC PDR, unbounded", "no overflow/underflow, 1-bit gray steps, data order, with two free clocks", "PASS"],
        ["Credits", "ABC PDR, unbounded", "credits stay in [0, MAX]; conservation even with late or lost credit returns", "PASS"],
        ["Replay buffer", "k-induction", "ack <= rd <= wr, window <= depth, full never accepts", "PASS"],
        ["Go-Back-N link", "ABC PDR, unbounded", "delivered stream is exactly 0, 1, 2, ... over a lossy channel", "PASS"],
        ["Training FSM", "BMC, depth 20", "legal states; ACTIVE only with lock; FAILED only after the budget", "PASS"]]
y = table(data, M, y - 2, [74, 92, CW - 214, 48])
y -= 16
cov = json.load(open(COV))
y = section(M, y, "Functional coverage: 233 / 233 bins = 100%   (bins per coverage item, all hit)", TEAL)
items = sorted(((k.replace("d2d.", ""), len(v), sum(1 for h in v.values() if h)) for k, v in cov.items()),
               key=lambda t: -t[1])
mxb = max(n for _, n, _ in items)
colw2 = (CW - 20) / 2
for i, (k, n, hit) in enumerate(items):
    col, row = i // 10, i % 10
    x = M + col * (colw2 + 20)
    yy = y - 4 - row * 13
    text(x, yy - 9, k, "Mono", 6.8, INK)
    bw = (colw2 - 140) * n / mxb
    rrect(x + 118, yy - 10.5, max(bw, 2), 8, 2, TEAL)
    text(x + 122 + bw, yy - 9, f"{hit}/{n}", "UI", 6.6, SUB)
c.showPage()

# ================================================================== PAGE 8 - results, lessons, design Q&A
y = page_frame(8, "Steps 7 + 8", "Results, lessons and design Q&A",
               "What was found, what it costs in silicon, and why it is built this way")
yl = section(M, y, "The real RTL bug the tests caught", RED)
yl = callout(M, yl - 2, COL, "AXI READY high while the block was still in reset",
             "When reset is released at the pin, each domain's internal reset stays active for 2 more clocks (the "
             "synchronizer). In that window the slave's <font name='Mono'>AWREADY</font> was built from reset values and "
             "read 1. A host starting right after reset had its write \"accepted\", then silently lost, and the bus hung. "
             "<b>Caught by</b> <font name='Mono'>reset_during_traffic</font>. <b>Fix:</b> qualify AWREADY, ARREADY, WREADY "
             "and PREADY with the synchronized reset.", RED_L, RED)
yl = para("Also logged: one design characterization (at a 3% flit error rate the link correctly escalates to FAILED, "
          "because the retrain threshold is about 3.1%) and 5 testbench bugs. No check was weakened to make a test pass.",
          M, yl - 8, COL, BODY_S)
yl = section(M, yl - 16, "Synthesis estimates (Yosys 0.33 + SKY130 HD)")
areas = [("die_a_top", 179397), ("die_b_top", 175826), ("link_layer", 89296), ("async_fifo 80x16", 52577),
         ("replay_buffer", 50064), ("flit_rx", 17402), ("flit_tx", 13319), ("crc16", 7535), ("apb_csr", 5672)]
for i, (n, a) in enumerate(areas):
    yy = yl - 4 - i * 15
    text(M, yy - 9, n, "UI", 7.6, INK)
    bw = (COL - 152) * a / 179397
    rrect(M + 84, yy - 11, max(bw, 2), 10, 2, BLUE if i < 2 else TEAL)
    text(M + 88 + bw, yy - 9, f"{a:,} um\u00b2", "UI", 7, SUB)
yl -= 4 + len(areas) * 15 + 4
yl = para("Standard-cell area only, no routing. The worst combinational path is about <b>20.8 ns</b> (replay-buffer mux "
          "into the 112-bit CRC), which suggests roughly <b>48 MHz</b> in SKY130 at the typical corner. Both are "
          "<b>estimates</b>: no wires, no clock tree, no OpenSTA. Next steps: pipeline the CRC check and use SRAM instead "
          "of about 2,600 flops per die for the buffers.", M, yl, COL, BODY_S)

x2 = M + COL + GAP
yr = section(x2, y, "Common design questions", BLUE)
qa = [("Why cumulative ACK and credit counts?",
       "An increment lost with a corrupted flit is gone for good: a credit leaks and the link eventually deadlocks. A "
       "running total heals itself: the next good flit carries it and the transmitter takes the difference."),
      ("Why keep the retry window under half the SEQ space?",
       "The receiver classifies (seq - expected) mod 256: below 128 is a gap (NAK), otherwise a duplicate (drop). A "
       "window of 16 keeps the two cases from overlapping."),
      ("How do credits cross clock domains safely?",
       "The receive buffer is the async FIFO. Its gray read pointer, already synchronized into clk_link, counts freed "
       "slots. It lags, so credits return late, never early."),
      ("How did you avoid protocol deadlock?",
       "Separate REQ and RSP credits, plus credits spent once at enqueue, so a replay never needs new buffer space."),
      ("What limits the clock frequency?",
       "The 112-bit parallel CRC on the send and receive paths. Register the CRC check, or compute it per 32-bit beat.")]
yy = yr - 2
for q, a in qa:
    p = Paragraph(a, ParagraphStyle("qa", parent=BODY_S, fontSize=7.8, leading=10.4))
    _, ph = p.wrap(COL - 22, 300)
    hh = ph + 27
    rrect(x2, yy - hh, COL, hh, 6, BG, LINE)
    c.setFillColor(BLUE)
    c.circle(x2 + 12, yy - 12.5, 6.2, fill=1, stroke=0)
    text(x2 + 12, yy - 15.2, "Q", "UI-B", 7, white, "c")
    text(x2 + 23, yy - 15.5, q, "UI-B", 8, NAVY)
    p.drawOn(c, x2 + 11, yy - 22 - ph)
    yy -= hh + 6
yy -= 4
rrect(x2, yy - 96, COL, 96, 6, NAVY)
text(x2 + 12, yy - 16, "Reproduce everything", "UI-B", 8.5, MINT)
cmds = ["make image    # build the tool container", "make lint     # Verilator -Wall + Verible",
        "make unit     # block-level cocotb tests", "make regress  # all tests, 2 seeds, 15-min cap",
        "make formal   # SymbiYosys proofs", "make syn      # Yosys + SKY130 estimates"]
for i, s in enumerate(cmds):
    text(x2 + 12, yy - 31 - i * 11.2, s, "Mono", 7.4, HexColor("#E2E8F0"))
yr = yy - 96
y = min(yl, yr) - 16
y = section(M, y, "Honest limitations", AMB)
lims = [("Throughput", "Die B runs one transaction at a time, and each AXI beat uses a whole flit."),
        ("Scope", "Only INCR bursts verified; both dies assumed to reset together; FAILED needs software."),
        ("Faults", "Injected errors stay within CRC-16's guaranteed detection envelope."),
        ("SV UVM", "uvm_sv/ is syntax-checked only; it is meant to run on EDA Playground.")]
lw = (CW - 3 * 8) / 4
hmax = 0
for i, (t, d) in enumerate(lims):
    card(M + i * (lw + 8), y - 2, lw, t, d, fill=AMB_L, stroke=None, tcol=AMB, size=7.4, minh=70)
y -= 88
rrect(M, y - 74, CW, 74, 8, NAVY)
text(M + 14, y - 18, "THREE TAKEAWAYS", "UI-SB", 8, MINT)
take = [("Design for loss", "Cumulative ACKs and credits make every control field self-healing."),
        ("Cross clocks one way", "Eight gray-pointer FIFOs, and nothing else, cross between domains."),
        ("Back every claim", "Each number traces to a log: regression, coverage, formal, synthesis.")]
tw3 = (CW - 28 - 20) / 3
for i, (t, d) in enumerate(take):
    x = M + 14 + i * (tw3 + 10)
    text(x, y - 36, t, "UI-B", 9.5, white)
    para(d, x, y - 41, tw3, ParagraphStyle("tk", parent=BODY_S, fontSize=7.8, leading=10, textColor=HexColor("#CBD5E1")))
c.showPage()
c.save()
print("wrote", OUT)
