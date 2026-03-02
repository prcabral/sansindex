#!/usr/bin/env python3
"""
SANS Exam Index Builder

Build a hierarchical index (Topic → Sub topic) with book/page references.
Output formats (all alphabetical, 2-column where applicable):
  - PDF (ReportLab, pip-only)
  - HTML (open in browser, print-to-PDF friendly)
  - Markdown (plain text, good for notes/git)
  - LaTeX (optional, for TeX users)

Keybinds:
  1/a - Create a topic and set as current topic
  2/s - Create a subtopic under the current topic
  3/d - Create a topic + subtopic (does not change current topic)
  b   - Change current book number
  w   - Save progress
  g   - Generate all formats (PDF, HTML, Markdown, LaTeX)
  q   - Quit (saves first)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from sans_courses import SANS_COURSES
except ImportError:
    SANS_COURSES = {}


def clear_screen() -> None:
    """Clear terminal so each return to the main prompt shows a clean screen."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Optional: single-key input on Unix
try:
    import tty
    import termios
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

# --- Config: keybinds and defaults ---
KEY_TOPIC = ("1", "a")           # Create topic, update current
KEY_SUBTOPIC = ("2", "s")        # Create subtopic under current topic
KEY_TOPIC_SUBTOPIC = ("3", "d")  # Create topic + subtopic, don't update current
KEY_BOOK = "b"                   # Change book
KEY_SAVE = "w"                   # Save progress
KEY_GENERATE = "g"               # Generate all formats
KEY_QUIT = "q"                   # Quit

STATE_FILE = "index_state.json"
LATEX_FILE = "index.tex"
HTML_FILE = "index.html"
MD_FILE = "index.md"
DEFAULT_NUM_BOOKS = 6


def get_key(prompt: str = "") -> str:
    """Read a single key. Fallback to line input if no TTY or Windows."""
    if prompt:
        print(prompt, end="", flush=True)
    if HAS_TERMIOS and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1).lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print(ch)
        return ch
    line = input().strip().lower()
    return line[0] if line else ""


def get_line(prompt: str, default: str = "") -> str:
    """Read a line; return default if user hits Enter and default is set."""
    if default:
        s = input(f"{prompt} [{default}]: ").strip()
        return s if s else default
    return input(f"{prompt}: ").strip()


def sanitize_course_name(name: str) -> str:
    """Allow only SEC/FOR/ICS etc. style names."""
    name = name.strip().upper()
    if not re.match(r"^[A-Z]{3}\d{3}$", name):
        raise ValueError("Course number should be like SEC501, FOR508, ICS410, etc.")
    return name


def course_folder(base_dir: Path, course: str) -> Path:
    """Path to the course output folder."""
    return base_dir / course


def load_state(folder: Path) -> dict:
    path = folder / STATE_FILE
    if not path.exists():
        return {
            "course": "",
            "course_title": "",
            "num_books": DEFAULT_NUM_BOOKS,
            "current_book": 1,
            "current_topic_index": -1,
            "current_page": 0,
            "topics": [],
        }
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Ensure structure
    data.setdefault("course_title", "")
    data.setdefault("num_books", DEFAULT_NUM_BOOKS)
    data.setdefault("current_book", 1)
    data.setdefault("current_topic_index", -1)
    data.setdefault("current_page", 0)
    data.setdefault("topics", [])
    for t in data["topics"]:
        t.setdefault("subtopics", [])
        t.setdefault("book", 1)
        t.setdefault("page", 0)
        for s in t["subtopics"]:
            s.setdefault("book", 1)
            s.setdefault("page", 0)
    return data


def save_state(folder: Path, state: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / STATE_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print("  Progress saved.")


def add_topic(state: dict, title: str, book: int, page: int, set_current: bool = True) -> None:
    title = title.strip()
    if not title:
        return
    state["topics"].append({
        "title": title,
        "book": book,
        "page": page,
        "subtopics": [],
    })
    if set_current:
        state["current_topic_index"] = len(state["topics"]) - 1
    print(f"  Topic added: {title} ({book} - {page})")


def add_subtopic(state: dict, title: str, book: int, page: int) -> bool:
    title = title.strip()
    if not title:
        return False
    idx = state["current_topic_index"]
    if idx < 0 or idx >= len(state["topics"]):
        print("  No current topic. Use key 1 or 3 first.")
        return False
    state["topics"][idx]["subtopics"].append({
        "title": title,
        "book": book,
        "page": page,
    })
    print(f"  Subtopic added: {title} ({book} - {page})")
    return True


def change_book(state: dict) -> None:
    n = state.get("num_books", DEFAULT_NUM_BOOKS)
    try:
        s = get_line(f"Book number (1-{n})", str(state["current_book"]))
        b = int(s)
        if 1 <= b <= n:
            state["current_book"] = b
            print(f"  Current book set to {b}.")
        else:
            print(f"  Enter a number between 1 and {n}.")
    except ValueError:
        print("  Invalid number.")


def sort_index(state: dict) -> None:
    """Sort topics and subtopics alphabetically (case-insensitive)."""
    state["topics"].sort(key=lambda t: t["title"].lower())
    for t in state["topics"]:
        t["subtopics"].sort(key=lambda s: (s["title"].lower(), s["book"], s["page"]))


def _index_title(state: dict) -> str:
    """Full title for index: course code + optional course name."""
    code = state.get("course", "SANS")
    title = (state.get("course_title") or "").strip()
    return f"{code} — {title}" if title else f"{code} Exam Index"


def _page_ref(book: int, page: int) -> str:
    """Page reference format: X - YY (e.g. 1 - 42)."""
    return f"{book} - {page}"


# Footer text for this project (appears on all outputs)
PROJECT_FOOTER = "Generated by SANS Index Builder. For personal study use."


def generate_latex(state: dict, out_path: Path) -> None:
    """Write LaTeX file (2-column, compact, alphabetical)."""
    sort_index(state)
    course = state.get("course", "SANS")
    index_title = _index_title(state)
    lines = [
        r"\documentclass[9pt,a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{geometry}",
        r"\geometry{margin=0.5in, top=0.5in, bottom=0.5in}",
        r"\usepackage{multicol}",
        r"\usepackage{titlesec}",
        r"\usepackage{xcolor}",
        r"\usepackage{enumitem}",
        r"\usepackage{fancyhdr}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyhead[C]{\footnotesize\color{gray} " + index_title.replace("—", "--").replace("&", r"\&").replace("#", r"\#").replace("_", r"\_") + r"}",
        r"\renewcommand{\headrulewidth}{0.3pt}",
        r"\definecolor{accent}{RGB}{0,51,102}",
        r"\titleformat{\section}{\color{accent}\normalsize\bfseries}{}{0em}{}",
        r"\setlength{\columnsep}{0.4cm}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0pt}",
        r"\setlist{leftmargin=1em, itemsep=0pt, topsep=0pt, partopsep=0pt, nosep}",
        r"\begin{document}",
        r"\twocolumn",
        r"\begin{center}",
        r"\section*{\vspace{-0.2em}" + index_title.replace("—", "--").replace("&", r"\&").replace("#", r"\#").replace("_", r"\_") + r"}",
        r"\end{center}",
        r"\vspace{-0.3em}",
        "",
    ]
    for t in state["topics"]:
        title_esc = t["title"].replace("&", r"\&").replace("#", r"\#").replace("_", r"\_")
        topic_ref = _page_ref(t.get("book", 1), t.get("page", 0))
        lines.append(r"\noindent\textbf{\small " + title_esc + r"}\hfill{\scriptsize\textit{" + topic_ref + "}}")
        if t["subtopics"]:
            lines.append(r"\vspace{-0.2em}\begin{itemize}[leftmargin=*]")
            for s in t["subtopics"]:
                sub_esc = s["title"].replace("&", r"\&").replace("#", r"\#").replace("_", r"\_")
                ref = _page_ref(s["book"], s["page"])
                lines.append(r"  \item \small " + sub_esc + r"\hfill{\scriptsize\textit{" + ref + "}}")
            lines.append(r"\end{itemize}\vspace{0.2em}")
        else:
            lines.append(r"\vspace{0.1em}")
    footer_esc = PROJECT_FOOTER.replace("&", r"\&").replace("#", r"\#").replace("_", r"\_")
    lines.append(r"\vfill")
    lines.append(r"\noindent\begin{center}\scriptsize\textit{" + footer_esc + r"}\end{center}")
    lines.append(r"\end{document}")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  LaTeX written to {out_path}")


def _escape_html(s: str) -> str:
    """Escape for ReportLab Paragraph (HTML-like)."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if HAS_REPORTLAB:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    class _DotLeaderRow(Table):
        """A single-row Table that draws dot leaders between text and page ref,
        with optional background shading for alternating rows or accent bars."""

        def __init__(self, text_para, ref_para, col_width, ref_width_pt,
                     bg_color=None, dot_color=None, left_pad=0,
                     raw_text="", font_name="Helvetica", font_size=8, text_indent=0):
            self._bg_color = bg_color
            self._dot_color = dot_color or colors.HexColor("#cccccc")
            self._left_pad = left_pad
            self._raw_text = raw_text
            self._font_name = font_name
            self._font_size = font_size
            self._text_indent = text_indent
            super().__init__(
                [[text_para, ref_para]],
                colWidths=[col_width - ref_width_pt, ref_width_pt],
            )
            self.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (0, -1), self._left_pad),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))

        def drawOn(self, canvas, x, y, _sW=0):
            # Draw optional background shading
            if self._bg_color:
                canvas.saveState()
                canvas.setFillColor(self._bg_color)
                canvas.setStrokeColor(self._bg_color)
                canvas.rect(x, y, self._width, self._height, fill=1, stroke=0)
                canvas.restoreState()
            # Draw dot leaders between text and ref columns
            canvas.saveState()
            canvas.setFillColor(self._dot_color)
            canvas.setFont("Helvetica", 4)
            text_w = stringWidth(self._raw_text, self._font_name, self._font_size)
            dot_start_x = x + self._left_pad + self._text_indent + text_w + 3
            dot_end_x = x + self._colWidths[0] - 2
            dot_y = y + self._height / 2 - 1
            if dot_end_x - dot_start_x > 6:
                dot_x = dot_start_x
                while dot_x < dot_end_x:
                    canvas.drawString(dot_x, dot_y, ".")
                    dot_x += 3
            canvas.restoreState()
            # Draw the table content on top
            super().drawOn(canvas, x, y, _sW)

    class _LetterDivider(Table):
        """Full-width coloured bar showing a single letter as a section divider."""

        _letter_style = None

        def __init__(self, letter, col_width):
            if _LetterDivider._letter_style is None:
                _LetterDivider._letter_style = ParagraphStyle(
                    "LetterDivider",
                    fontSize=9,
                    fontName="Helvetica-Bold",
                    textColor=colors.HexColor("#ffffff"),
                    leading=12,
                    spaceBefore=0,
                    spaceAfter=0,
                )
            para = Paragraph(letter, _LetterDivider._letter_style)
            super().__init__(
                [[para]],
                colWidths=[col_width],
            )
            self.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0d47a1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))


def generate_pdf(state: dict, out_path: Path) -> bool:
    """Generate 2-column PDF with ReportLab (compact, pip-only)."""
    if not HAS_REPORTLAB:
        print("  Install reportlab: pip install reportlab")
        return False
    sort_index(state)
    index_title = _index_title(state)
    topic_count = len(state["topics"])
    margin = 0.5 * inch
    width, height = A4
    title_height = 0.55 * inch
    gap = 0.08 * inch
    col_gap = 0.3 * inch
    footer_height = 0.25 * inch
    col_width = (width - 2 * margin - col_gap) / 2
    content_height = height - 2 * margin - title_height - gap - footer_height
    # First page: full-width top frame for title, then two columns
    top_frame = Frame(margin, height - margin - title_height, width - 2 * margin, title_height, id="top")
    left_frame = Frame(margin, margin + footer_height, col_width, content_height, id="left")
    right_frame = Frame(margin + col_width + col_gap, margin + footer_height, col_width, content_height, id="right")
    # Later pages: two columns only (no top frame)
    content_height_rest = height - 2 * margin - footer_height
    left_rest = Frame(margin, margin + footer_height, col_width, content_height_rest, id="left_rest")
    right_rest = Frame(margin + col_width + col_gap, margin + footer_height, col_width, content_height_rest, id="right_rest")

    # Colors
    topic_accent_bg = colors.HexColor("#e8f0fe")
    alt_row_bg = colors.HexColor("#f5f7fa")
    dot_leader_color = colors.HexColor("#bbbbbb")

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawCentredString(width / 2, margin + footer_height * 0.25, PROJECT_FOOTER)
        page_num_text = f"Page {doc.page}"
        canvas.drawRightString(width - margin, margin + footer_height * 0.25, page_num_text)
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[top_frame, left_frame, right_frame], onPage=draw_footer),
        PageTemplate(id="rest", frames=[left_rest, right_rest], onPage=draw_footer),
    ])
    styles = getSampleStyleSheet()
    topic_style = ParagraphStyle(
        "Topic",
        parent=styles["Normal"],
        fontSize=8,
        spaceBefore=0,
        spaceAfter=0,
        textColor=colors.HexColor("#0d47a1"),
        leftIndent=4,
        fontName="Helvetica-Bold",
        leading=10,
    )
    item_style = ParagraphStyle(
        "Item",
        parent=styles["Normal"],
        fontSize=7.5,
        leftIndent=14,
        spaceBefore=0,
        spaceAfter=0,
        textColor=colors.HexColor("#1a1a1a"),
        leading=9,
    )
    ref_style = ParagraphStyle(
        "Ref",
        parent=styles["Normal"],
        fontSize=6,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#6b6b6b"),
        rightIndent=2,
        spaceBefore=0,
        spaceAfter=0,
    )
    ref_width_pt = 30
    title_centered = ParagraphStyle(
        "TitleCenter",
        parent=styles["Normal"],
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=0,
        spaceBefore=0,
        textColor=colors.HexColor("#0d47a1"),
        fontName="Helvetica-Bold",
        leading=13,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=7,
        alignment=TA_CENTER,
        spaceAfter=0,
        spaceBefore=1,
        textColor=colors.HexColor("#888888"),
        fontName="Helvetica-Oblique",
        leading=9,
    )

    # -- Build story --
    story = []
    story.append(Paragraph(f'<b>{_escape_html(index_title)}</b>', title_centered))
    story.append(Paragraph(f'{topic_count} topics indexed', subtitle_style))
    story.append(Spacer(1, gap))
    story.append(NextPageTemplate("rest"))

    current_letter = ""
    for t in state["topics"]:
        first_letter = t["title"][0].upper() if t["title"] else "?"

        # Alphabetical letter divider
        if first_letter != current_letter:
            if current_letter:
                story.append(Spacer(1, 6))
            current_letter = first_letter
            story.append(_LetterDivider(current_letter, col_width))
            story.append(Spacer(1, 2))

        # Topic row with light blue accent background and dot leaders
        topic_ref = _page_ref(t.get("book", 1), t.get("page", 0))
        topic_text_para = Paragraph(_escape_html(t["title"]), topic_style)
        ref_para = Paragraph(f'<i>{topic_ref}</i>', ref_style)
        topic_row = _DotLeaderRow(
            topic_text_para, ref_para, col_width, ref_width_pt,
            bg_color=topic_accent_bg, dot_color=dot_leader_color, left_pad=0,
            raw_text=t["title"], font_name="Helvetica-Bold", font_size=8, text_indent=4,
        )
        story.append(topic_row)

        # Subtopic rows with alternating shading and dot leaders
        for si, s in enumerate(t["subtopics"]):
            ref = _page_ref(s["book"], s["page"])
            item_para = Paragraph(_escape_html(s["title"]), item_style)
            ref_para = Paragraph(f'<i>{ref}</i>', ref_style)
            row_bg = alt_row_bg if si % 2 == 1 else None
            sub_row = _DotLeaderRow(
                item_para, ref_para, col_width, ref_width_pt,
                bg_color=row_bg, dot_color=dot_leader_color, left_pad=0,
                raw_text=s["title"], font_name="Helvetica", font_size=7.5, text_indent=14,
            )
            story.append(sub_row)

        # Visual separator between topic groups
        story.append(Spacer(1, 4))

    try:
        doc.build(story)
        print(f"  PDF written to {out_path}")
        return True
    except Exception as e:
        print("  PDF error:", e)
        return False


def generate_html(state: dict, out_path: Path) -> None:
    """Write 2-column HTML (compact, print-friendly)."""
    sort_index(state)
    index_title = _index_title(state)
    index_title_esc = _escape_html(index_title)
    total_topics = len(state["topics"])

    # Build body with alphabetical letter dividers
    items_html = []
    current_letter = ""
    for t in state["topics"]:
        first_char = t["title"][0].upper() if t["title"] else ""
        if first_char and first_char != current_letter:
            current_letter = first_char
            items_html.append(
                f'<div class="letter-divider" aria-label="Section {current_letter}">{current_letter}</div>'
            )
        title_esc = _escape_html(t["title"])
        topic_ref = _page_ref(t.get("book", 1), t.get("page", 0))
        sub_items = "".join(
            f'<li><span class="sub">{_escape_html(s["title"])}</span> '
            f'<span class="ref">{_page_ref(s["book"], s["page"])}</span></li>'
            for s in t["subtopics"]
        )
        # Only render <ul> when there are subtopics
        sub_block = f"<ul>{sub_items}</ul>" if t["subtopics"] else ""
        items_html.append(
            f'<section class="topic"><div class="topic-head">'
            f'<span class="sub">{title_esc}</span>'
            f'<span class="ref">{topic_ref}</span></div>{sub_block}</section>'
        )
    body = "\n".join(items_html)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{index_title_esc}</title>
  <style>
    :root {{
      --ink: #1e293b;
      --muted: #64748b;
      --accent: #0d47a1;
      --accent-soft: #e8eef6;
      --border: #e2e8f0;
      --bg: #fafbfc;
      --card: #ffffff;
      --zebra: #f5f7fa;
      --leader-dot: #c0c8d4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      color: var(--ink);
      margin: 0;
      padding: 0.5in;
      font-size: 12px;
      line-height: 1.4;
      max-width: 100%;
      background: var(--bg);
    }}
    .page-title {{
      font-size: 1.35rem;
      font-weight: 700;
      margin: 0 0 0.15rem 0;
      color: var(--accent);
      letter-spacing: 0.02em;
      text-align: center;
      padding-bottom: 0.4rem;
      border-bottom: 2px solid var(--border);
    }}
    .summary-line {{
      text-align: center;
      font-size: 0.75rem;
      color: var(--muted);
      margin: 0.1rem 0 0.5rem 0;
      letter-spacing: 0.01em;
    }}
    /* --- Alphabetical letter dividers --- */
    .letter-divider {{
      break-inside: avoid;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--muted);
      letter-spacing: 0.08em;
      padding: 0.35rem 0 0.15rem 0.2rem;
      margin-top: 0.3rem;
      border-bottom: 1px solid var(--border);
    }}
    .cols {{
      column-count: 2;
      column-gap: 1.5rem;
      column-fill: balance;
      margin-top: 0.5rem;
    }}
    .topic {{
      break-inside: avoid;
      margin-bottom: 0.5rem;
      padding: 0.35rem 0.5rem 0.3rem 0.6rem;
      background: var(--card);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      border-radius: 0 4px 4px 0;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}
    /* --- Enhanced topic head --- */
    .topic-head {{
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 0.2rem;
      display: flex;
      align-items: baseline;
      gap: 0;
      line-height: 1.3;
      background: var(--accent-soft);
      margin: -0.35rem -0.5rem 0.2rem -0.6rem;
      padding: 0.35rem 0.5rem 0.25rem 0.6rem;
      border-radius: 0 3px 0 0;
    }}
    /* Dot leader shared pattern (flex row with overflow dots) */
    .topic-head .sub,
    .topic li .sub {{
      flex: 1;
      min-width: 0;
      overflow: hidden;
      white-space: nowrap;
    }}
    .topic-head .sub::after,
    .topic li .sub::after {{
      content: " ........................................................................................................";
      color: var(--leader-dot);
      font-weight: 400;
      letter-spacing: 0.12em;
      font-size: 0.65rem;
    }}
    .topic-head .ref,
    .topic li .ref {{
      flex-shrink: 0;
      white-space: nowrap;
    }}
    .topic ul {{
      list-style: none;
      padding: 0;
      margin: 0;
      border-top: 1px solid var(--border);
      padding-top: 0.2rem;
      margin-top: 0.2rem;
    }}
    .topic li {{
      font-size: 0.8rem;
      margin: 0;
      padding: 0.15rem 0.15rem 0.1rem 0.15rem;
      display: flex;
      align-items: baseline;
      gap: 0;
      line-height: 1.4;
      color: var(--ink);
      border-bottom: 1px solid transparent;
      border-radius: 2px;
    }}
    /* Alternating row shading on subtopics */
    .topic li:nth-child(even) {{
      background: var(--zebra);
    }}
    .topic li:hover {{ background: var(--accent-soft); }}
    .topic li:last-child {{ border-bottom: none; }}
    .ref {{
      font-size: 0.7rem;
      color: var(--muted);
      flex-shrink: 0;
      font-variant-numeric: tabular-nums;
      min-width: 3.8em;
      text-align: right;
      font-weight: 500;
      padding-left: 0.2rem;
    }}
    .topic-head .ref {{
      font-size: 0.75rem;
      color: var(--accent);
      font-weight: 600;
    }}
    @media print {{
      body {{ padding: 0.4in; background: #fff; font-size: 11px; }}
      .page-title {{ border-bottom-color: #ccc; }}
      .summary-line {{ color: #888; }}
      .letter-divider {{ color: #888; border-bottom-color: #ccc; }}
      .cols {{ column-gap: 1rem; margin-top: 0.3rem; }}
      .topic {{
        margin-bottom: 0.35rem;
        padding: 0.25rem 0.4rem 0.2rem 0.5rem;
        box-shadow: none;
        border: 1px solid #e0e0e0;
      }}
      .topic-head {{
        background: #f0f4f8;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      /* Preserve alternating shading in print */
      .topic li:nth-child(even) {{
        background: #f5f7fa;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      /* Preserve dot leaders in print */
      .topic-head .sub::after,
      .topic li .sub::after {{
        color: #c0c0c0;
      }}
      .topic li:hover {{ background: transparent; }}
    }}
    .footer {{
      margin-top: 1.5rem;
      padding-top: 0.5rem;
      border-top: 1px solid var(--border);
      font-size: 0.7rem;
      color: var(--muted);
      text-align: center;
    }}
    @media print {{ .footer {{ margin-top: 1rem; font-size: 0.65rem; }} }}
  </style>
</head>
<body>
  <h1 class="page-title">{index_title_esc}</h1>
  <p class="summary-line">{total_topics} topic{"s" if total_topics != 1 else ""} indexed</p>
  <div class="cols">
{body}
  </div>
  <p class="footer">{_escape_html(PROJECT_FOOTER)}</p>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    print(f"  HTML written to {out_path}")


def generate_markdown(state: dict, out_path: Path) -> None:
    """Write Markdown (compact, good for notes and version control)."""
    sort_index(state)
    index_title = _index_title(state)
    lines = [f"# {index_title}", ""]
    for t in state["topics"]:
        lines.append(f"**{t['title']}**  {_page_ref(t.get('book', 1), t.get('page', 0))}")
        for s in t["subtopics"]:
            lines.append(f"  - {s['title']}  {_page_ref(s['book'], s['page'])}")
        lines.append("")
    lines.append("---")
    lines.append(f"*{PROJECT_FOOTER}*")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown written to {out_path}")


def run_key_1(state: dict) -> None:
    title = get_line("Topic name")
    if not title.strip():
        return
    page_s = get_line("Page number (for topic)", "0")
    try:
        page = int(page_s)
    except ValueError:
        page = 0
    state["current_page"] = page
    add_topic(state, title, state["current_book"], page, set_current=True)


def run_key_2(state: dict) -> None:
    title = get_line("Subtopic name")
    if not title.strip():
        return
    next_page = state.get("current_page", 0) + 1
    page_s = get_line("Page number", str(next_page))
    try:
        page = int(page_s)
    except ValueError:
        page = next_page
    state["current_page"] = page
    add_subtopic(state, title, state["current_book"], page)


def run_key_3(state: dict) -> None:
    topic_title = get_line("New topic name")
    if not topic_title.strip():
        return
    cur_page = state.get("current_page", 0)
    page_s = get_line("Page number", str(cur_page))
    try:
        page = int(page_s)
    except ValueError:
        page = cur_page
    state["current_page"] = page
    add_topic(state, topic_title, state["current_book"], page, set_current=False)
    add_subtopic(state, topic_title, state["current_book"], page)


def show_status(state: dict) -> None:
    idx = state["current_topic_index"]
    current = state["topics"][idx]["title"] if 0 <= idx < len(state["topics"]) else "(none)"
    print(f"\n  Book: {state['current_book']}  |  Page: {state.get('current_page', 0)}  |  Current topic: {current}  |  Topics: {len(state['topics'])}")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    print("SANS Exam Index Builder")
    print("----------------------")

    course = ""
    while not course:
        raw = get_line("Course number (e.g. SEC501, FOR508, ICS410)")
        try:
            course = sanitize_course_name(raw)
        except ValueError as e:
            print(e)

    folder = course_folder(base_dir, course)
    folder.mkdir(parents=True, exist_ok=True)
    state = load_state(folder)
    state["course"] = course
    known_name = SANS_COURSES.get(course)
    if known_name:
        state["course_title"] = known_name
        print(f"  Course: {known_name}")
    else:
        course_title = get_line("Course name (e.g. Advanced Security Essentials)", state.get("course_title", "")).strip()
        if course_title:
            state["course_title"] = course_title
    if state["topics"]:
        print(f"Loaded existing index: {len(state['topics'])} topics.")
    else:
        print(f"New index for {course}. Results in: {folder}")

    # Optional: set number of books once
    if state.get("num_books") == DEFAULT_NUM_BOOKS:
        n = get_line(f"Number of books (Enter = {DEFAULT_NUM_BOOKS})", str(DEFAULT_NUM_BOOKS))
        try:
            state["num_books"] = max(1, int(n))
        except ValueError:
            pass

    while True:
        clear_screen()
        show_status(state)
        print("  1/a=Topic  2/s=Subtopic  3/d=Topic+Subtopic  b=Book  w=Save  g=Generate all  q=Quit")
        k = get_key("Key: ")

        if k == KEY_QUIT:
            save_state(folder, state)
            print("Bye.")
            break
        if k == KEY_SAVE:
            save_state(folder, state)
            continue
        if k == KEY_BOOK:
            change_book(state)
            continue
        if k == KEY_GENERATE:
            save_state(folder, state)
            generate_pdf(state, folder / "index.pdf")
            generate_html(state, folder / HTML_FILE)
            generate_markdown(state, folder / MD_FILE)
            generate_latex(state, folder / LATEX_FILE)
            print("  Resuming in 3s...")
            time.sleep(3)
            continue
        if k in KEY_TOPIC:
            run_key_1(state)
            save_state(folder, state)
            continue
        if k in KEY_SUBTOPIC:
            if run_key_2(state):
                save_state(folder, state)
            continue
        if k in KEY_TOPIC_SUBTOPIC:
            run_key_3(state)
            save_state(folder, state)
            continue
        print("  Unknown key. Use 1/a, 2/s, 3/d, b, w, g, q.")


if __name__ == "__main__":
    main()
