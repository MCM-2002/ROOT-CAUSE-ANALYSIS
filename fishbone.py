"""Fishbone (Ishikawa) diagram layout and SVG rendering.

The layout adapts to the number and length of causes so labels never overlap:
causes wrap to multiple lines, and branch length grows with the tallest category.
"""
from __future__ import annotations

import re
import textwrap
from typing import Dict, Iterable, List, Tuple
from xml.sax.saxutils import escape

from models import CATEGORIES, CATEGORY_KEYS

# ---- Theme -----------------------------------------------------------------
NAVY = "#0B2545"
NAVY_MID = "#13315C"
BLUE = "#3E6AA8"
BLUE_LIGHT = "#E8EEF7"
GREY = "#5B6B7F"
WHITE = "#FFFFFF"
FONT = "Helvetica, Arial, sans-serif"

# ---- Layout constants ------------------------------------------------------
WIDTH = 1600
MARGIN_TOP = 70
BOX_W, BOX_H = 210, 40
PITCH = 380            # horizontal distance between neighbouring branches
FIRST_X = 290          # x of first branch at its outer end
SLANT = 120            # horizontal run of each branch toward the head
SPINE_X0 = 40
HEAD_X = 1210
HEAD_W = 360
CAUSE_FS = 13
LINE_H = 17
CAUSE_GAP = 11
TEXT_MAX_W = 250
CHAR_W = 0.55          # average glyph width as a fraction of font size
MIN_BRANCH = 230
MAX_CAUSE_CHARS = 160
MAX_PROBLEM_CHARS = 230

# Top row (left→right) and bottom row (left→right)
TOP_ROW = ["man", "method", "measurement"]
BOTTOM_ROW = ["machine", "material", "environment"]


def _wrap(text: str, font_size: float, max_width: float, bold: bool = False) -> List[str]:
    factor = CHAR_W * (1.08 if bold else 1.0)
    chars = max(8, int(max_width / (font_size * factor)))
    lines = textwrap.wrap(text, width=chars, break_long_words=True, break_on_hyphens=True)
    return lines or [""]


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _prepare(causes: Dict[str, Iterable]) -> Dict[str, List[Tuple[List[str], bool]]]:
    """Return {category: [(wrapped_lines, verified), ...]} skipping blank causes."""
    out: Dict[str, List[Tuple[List[str], bool]]] = {}
    for key in CATEGORY_KEYS:
        items = []
        for c in causes.get(key, []) or []:
            text = c if isinstance(c, str) else getattr(c, "text", "")
            verified = False if isinstance(c, str) else bool(getattr(c, "verified", False))
            text = _clip(text, MAX_CAUSE_CHARS)
            if not text.strip():
                continue
            items.append((_wrap(text, CAUSE_FS, TEXT_MAX_W), verified))
        out[key] = items
    return out


def _block_height(lines: List[str]) -> int:
    return len(lines) * LINE_H + CAUSE_GAP


def render_svg(problem: str, causes: Dict[str, Iterable], title: str = "Cause-and-Effect (Ishikawa) Diagram") -> str:
    """Render the full diagram as a standalone SVG string."""
    prepared = _prepare(causes)
    problem = _clip(problem or "Problem statement", MAX_PROBLEM_CHARS)

    # Branch length is driven by the tallest category.
    need = 0
    for items in prepared.values():
        need = max(need, sum(_block_height(lines) for lines, _ in items))
    branch_len = max(MIN_BRANCH, need + 40)

    box_top_y = MARGIN_TOP
    branch_top_y = box_top_y + BOX_H
    spine_y = branch_top_y + branch_len
    branch_bot_y = spine_y + branch_len
    box_bot_y = branch_bot_y
    legend_y = box_bot_y + BOX_H + 40
    height = legend_y + 40

    p: List[str] = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" font-family="{FONT}">'
    )
    p.append(f'<rect width="{WIDTH}" height="{height}" fill="{WHITE}"/>')
    # Header
    p.append(f'<rect x="0" y="0" width="{WIDTH}" height="8" fill="{NAVY}"/>')
    p.append(
        f'<text x="40" y="42" font-size="20" font-weight="bold" fill="{NAVY}" letter-spacing="0.5">{escape(title)}</text>'
    )

    # Spine + arrow into head
    p.append(f'<line x1="{SPINE_X0}" y1="{spine_y}" x2="{HEAD_X - 14}" y2="{spine_y}" stroke="{NAVY}" stroke-width="6" stroke-linecap="round"/>')
    p.append(
        f'<polygon points="{HEAD_X - 22},{spine_y - 13} {HEAD_X + 2},{spine_y} {HEAD_X - 22},{spine_y + 13}" fill="{NAVY}"/>'
    )

    # Head (problem statement)
    prob_lines = _wrap(problem, 16, HEAD_W - 40, bold=True)
    head_h = max(110, len(prob_lines) * 22 + 64)
    head_y = spine_y - head_h / 2
    p.append(f'<rect x="{HEAD_X}" y="{head_y}" width="{HEAD_W}" height="{head_h}" rx="12" fill="{NAVY}"/>')
    p.append(
        f'<text x="{HEAD_X + HEAD_W / 2}" y="{head_y + 26}" text-anchor="middle" font-size="11" '
        f'font-weight="bold" fill="#9FB6D6" letter-spacing="2">PROBLEM / EFFECT</text>'
    )
    ty = head_y + 54
    for ln in prob_lines:
        p.append(
            f'<text x="{HEAD_X + HEAD_W / 2}" y="{ty}" text-anchor="middle" font-size="16" font-weight="bold" fill="{WHITE}">{escape(ln)}</text>'
        )
        ty += 22

    # Branches
    def draw_row(keys: List[str], upper: bool) -> None:
        for i, key in enumerate(keys):
            x_top = FIRST_X + i * PITCH
            x_join = x_top + SLANT
            items = prepared[key]
            if upper:
                y_outer, y_inner = branch_top_y, spine_y
                box_y = box_top_y
            else:
                y_outer, y_inner = branch_bot_y, spine_y
                box_y = box_bot_y
            # Category box
            p.append(
                f'<rect x="{x_top - BOX_W / 2}" y="{box_y}" width="{BOX_W}" height="{BOX_H}" rx="6" fill="{NAVY_MID}"/>'
            )
            p.append(
                f'<text x="{x_top}" y="{box_y + BOX_H / 2 + 5}" text-anchor="middle" font-size="14" font-weight="bold" fill="{WHITE}">{escape(CATEGORIES[key])}</text>'
            )
            # Branch line
            p.append(
                f'<line x1="{x_top}" y1="{y_outer}" x2="{x_join}" y2="{y_inner}" stroke="{NAVY_MID}" stroke-width="3.5" stroke-linecap="round"/>'
            )
            # Causes
            cursor = (branch_top_y if upper else spine_y) + 20
            for lines, verified in items:
                text_h = len(lines) * LINE_H
                y_mid = cursor + text_h / 2
                if upper:
                    frac = (y_mid - branch_top_y) / branch_len
                else:
                    frac = 1 - (y_mid - spine_y) / branch_len
                x_b = x_top + SLANT * frac
                # Tick connecting the label to the branch
                p.append(
                    f'<line x1="{x_b - 12:.1f}" y1="{y_mid:.1f}" x2="{x_b:.1f}" y2="{y_mid:.1f}" stroke="{BLUE}" stroke-width="2"/>'
                )
                fill = NAVY if verified else WHITE
                p.append(
                    f'<circle cx="{x_b:.1f}" cy="{y_mid:.1f}" r="4.5" fill="{fill}" stroke="{NAVY}" stroke-width="1.8"/>'
                )
                # Multi-line label, right-aligned against the tick
                first_y = y_mid - text_h / 2 + LINE_H - 4
                weight = "bold" if verified else "normal"
                for j, ln in enumerate(lines):
                    p.append(
                        f'<text x="{x_b - 17:.1f}" y="{first_y + j * LINE_H:.1f}" text-anchor="end" '
                        f'font-size="{CAUSE_FS}" font-weight="{weight}" fill="#1B2A41">{escape(ln)}</text>'
                    )
                cursor += _block_height(lines)

    draw_row(TOP_ROW, upper=True)
    draw_row(BOTTOM_ROW, upper=False)

    # Legend
    p.append(f'<circle cx="46" cy="{legend_y}" r="4.5" fill="{WHITE}" stroke="{NAVY}" stroke-width="1.8"/>')
    p.append(
        f'<text x="58" y="{legend_y + 4}" font-size="12" fill="{GREY}">Potential cause (hypothesis, requires verification)</text>'
    )
    p.append(f'<circle cx="390" cy="{legend_y}" r="4.5" fill="{NAVY}" stroke="{NAVY}" stroke-width="1.8"/>')
    p.append(
        f'<text x="402" y="{legend_y + 4}" font-size="12" fill="{GREY}">Supporting evidence confirmed by user</text>'
    )
    p.append(f'<rect x="0" y="{height - 8}" width="{WIDTH}" height="8" fill="{NAVY}"/>')
    p.append("</svg>")
    return "\n".join(p)


def svg_size(svg: str) -> Tuple[int, int]:
    m = re.search(r'viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"', svg)
    if not m:
        return WIDTH, 900
    return int(float(m.group(1))), int(float(m.group(2)))
