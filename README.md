# SANS Index Builder

Build a study index for SANS course exams. Add topics and subtopics with book/page references, then export to PDF, HTML, Markdown, or LaTeX.

## Installation

Requires **Python 3.8+**.

```bash
git clone <repo-url> sansIndex
cd sansIndex
```

Install dependencies with [uv](https://docs.astral.sh/uv/) (recommended) or pip:

```bash
# uv
uv sync

# pip
pip install -r requirements.txt
```

Only dependency is `reportlab` (for PDF generation).

## Running

```bash
# uv
uv run sans_index.py

# pip
python sans_index.py
```

On first run:
1. Enter a course code (e.g. `SEC501`, `FOR508`, `ICS410`). A folder with that name is created; if it already exists, the existing index is loaded.
2. If the course is in the built-in list (~85 courses in `sans_courses.py`), the name auto-fills. Otherwise you're prompted.
3. Set number of books (default 6).
4. Use keybinds to add topics/subtopics. Press **g** to generate all output formats.

## Keybinds

| Key | Action |
|-----|--------|
| **1** / **a** | Create a **topic** and set as current topic |
| **2** / **s** | Create a **subtopic** under current topic |
| **3** / **d** | Create a **topic + subtopic** combo (does not change current topic) |
| **b** | Change current **book** number |
| **w** | **Save** progress |
| **g** | **Generate** all output formats |
| **q** | **Quit** (auto-saves) |

Progress auto-saves after each add. Screen clears between actions.

## Page defaults

When you skip the page prompt (just hit Enter), the default depends on the action:

- **Subtopic (2/s):** defaults to `current_page + 1` (next page)
- **Topic+Subtopic (3/d):** defaults to `current_page` (same page)
- **Topic (1/a):** always updates the tracked page

Current page shows in the status bar and persists across sessions.

## Output formats

Press **g** to generate all formats in the course folder:

| Format | File | Notes |
|--------|------|-------|
| PDF | `index.pdf` | 2-column, letter dividers, dot leaders, alternating row shading, page footers (ReportLab) |
| HTML | `index.html` | 2-column card layout, print-friendly CSS, dot leaders |
| Markdown | `index.md` | Plain text, good for notes/git |
| LaTeX | `index.tex` | For editing or compiling with TeX |

Everything is sorted alphabetically. Page refs look like `1 - 42` (book - page).

## Project layout

```
sansIndex/
├── sans_index.py       # Main app
├── sans_courses.py     # Course number → name lookup (~85 courses)
├── requirements.txt
├── .gitignore
├── example/
│   └── SEC501/         # Sample output for previewing formats
└── README.md
```

## Data storage

All state is saved to `<course>/index_state.json` (e.g. `SEC501/index_state.json`). Run again with the same course number to pick up where you left off.
