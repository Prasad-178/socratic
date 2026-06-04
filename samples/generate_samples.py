"""Generate fact-dense sample PDFs for testing socratic, across domains.

Each PDF's body HTML lives in samples/content/<name>.html (just the inner
markup: an <h1> then many <h2>/<p>/<ul> sections). This script wraps it with a
shared stylesheet and flows it across pages with PyMuPDF's Story API.

Run from the agent venv:  uv run --project agent python samples/generate_samples.py
"""
from pathlib import Path

import pymupdf

OUT = Path(__file__).parent
CONTENT = OUT / "content"

_CSS = """
h1 { font-size: 22px; margin-bottom: 6px; }
h2 { font-size: 15px; margin-top: 16px; margin-bottom: 3px; color: #1a1a1a; }
h3 { font-size: 12.5px; margin-top: 10px; margin-bottom: 2px; color: #333; }
p  { font-size: 11px; line-height: 1.5; margin: 5px 0; text-align: justify; }
li { font-size: 11px; line-height: 1.45; margin: 2px 0; }
"""

# pdf filename -> content html filename
DOCS: dict[str, str] = {
    "medical_hypertension.pdf": "medical_hypertension.html",
    "cs_tcp_udp.pdf": "cs_tcp_udp.html",
    "finance_time_value_money.pdf": "finance_time_value_money.html",
    "astronomy_star_lifecycle.pdf": "astronomy_star_lifecycle.html",
}


def build(filename: str, html: str) -> int:
    story = pymupdf.Story(html=html, user_css=_CSS)
    writer = pymupdf.DocumentWriter(str(OUT / filename))
    mediabox = pymupdf.paper_rect("letter")
    where = mediabox + (54, 54, -54, -54)
    pages = 0
    more = 1
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


if __name__ == "__main__":
    for pdf, html_file in DOCS.items():
        html = (CONTENT / html_file).read_text()
        n = build(pdf, html)
        print(f"  {pdf}: {n} pages  ({len(html.split())} words)")
    print(f"Wrote {len(DOCS)} sample PDFs to {OUT}")
