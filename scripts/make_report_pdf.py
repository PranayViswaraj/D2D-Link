"""Print scripts/report/d2d_report.html to docs/D2D-Link_Project_Report.pdf (12 pages, A4).
Numbers in the HTML are copied from docs/results.md and the logs it cites.
Usage (Windows host, needs Microsoft Edge or Google Chrome; fonts load from Google Fonts):
  python scripts/make_report_pdf.py [out.pdf]
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts" / "report" / "d2d_report.html"
OUT = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "docs" / "D2D-Link_Project_Report.pdf"

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
exe = next((b for b in BROWSERS if os.path.exists(b)), None)
if exe is None:
    sys.exit("no Edge or Chrome found")

subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                "--virtual-time-budget=15000", "--run-all-compositor-stages-before-draw",
                f"--print-to-pdf={OUT}", SRC.as_uri()], check=True, timeout=180)
print(f"wrote {OUT}")
