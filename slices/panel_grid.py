#!/usr/bin/env python3
"""
Fingerprint grid — the panel as one image (1200×630, og-image geometry).

Renders the frontier panel as an SVG heatmap: model rows × failure-mode columns,
cell shade = share of decided runs that FAILED the mode (absolute 0–100% scale, so
grids from future panels are directly comparable), cell text = passes/decided with
the Wilson 95% interval. Data comes from panel_stats.py — the same derivation the
README table uses; this script adds geometry only.

Design constraints applied (and why):
  - Sequential single-hue ramp (blue, light→dark), lightness-monotonic: shade encodes
    one magnitude. Dark = wounded is the fingerprint read; clean cells recede.
  - Absolute scale, not per-panel normalization: a future panel's grid must be
    comparable cell-for-cell, or the recurrence story breaks.
  - Every cell prints its numbers: sub-3:1 fills carry visible labels (relief rule).
  - Cells with decided n < 10 (the accepted mistral-large partials) are neutral grey
    and print n — they must not be read as measurements.

Output: assets/fingerprint-grid-2026-07.svg (deterministic; commit alongside the PNG).
Rasterize with any SVG renderer at 1200×630, e.g. a headless-browser screenshot.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from panel_stats import aggregate, load_panel, wilson  # noqa: E402

# Sequential blue ramp, 13 lightness-monotonic steps (reference palette; validated).
RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
        "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
INK_ON_DARK = "#ffffff"
GREY_CELL = "#f0efec"
HAIRLINE = "#e1e0d9"

LOW_N = 10  # decided < LOW_N renders neutral: a partial, not a measurement

MODES = [  # taxonomy order: (slice dir, header line 1, header line 2)
    ("source-overtrust", "1 source", "overtrust"),
    ("stale-recall", "2 stale", "recall"),
    ("confidence-calibration", "3 confidence", "calibration"),
    ("sycophancy", "4 sycophancy", ""),
    ("false-precision", "5 false", "precision"),
    ("overcorrection", "6 over-", "correction"),
    ("disconfirmation-avoidance", "7 disconfirm.", "avoidance"),
    ("premature-certification", "8 self-", "certification"),
]

W, H = 1200, 630
GRID_TOP, ROW_PITCH, CELL_H = 124, 64, 60
LABEL_W, GRID_LEFT, COL_PITCH, CELL_W = 190, 222, 96, 92
AGG_LEFT, AGG_W = 1002, 126


def shade(fail_share):
    idx = min(len(RAMP) - 1, int(fail_share * len(RAMP)))
    return RAMP[idx]


def luminance(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


def text(x, y, s, size, fill, weight="normal", anchor="middle"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'font-family="system-ui, -apple-system, \'Segoe UI\', sans-serif">{esc(s)}</text>')


def cell(x, y, w, counts):
    """One measured cell: shaded rect + passes/decided + CI."""
    dec = counts["pass"] + counts["fail"]
    parts = []
    if dec == 0:
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{CELL_H}" rx="4" fill="{GREY_CELL}"/>')
        parts.append(text(x + w / 2, y + CELL_H / 2 + 4, "—", 13, INK_MUTED))
        return parts
    if dec < LOW_N:
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{CELL_H}" rx="4" fill="{GREY_CELL}"/>')
        parts.append(text(x + w / 2, y + 26, f"{counts['pass']}/{dec}", 13, INK_MUTED, "600"))
        parts.append(text(x + w / 2, y + 44, "partial run", 10, INK_MUTED))
        return parts
    share = counts["fail"] / dec
    fill = shade(share)
    ink = INK_ON_DARK if luminance(fill) < 0.35 else INK
    sub = INK_ON_DARK if luminance(fill) < 0.35 else INK_SECONDARY
    lo, hi = wilson(counts["pass"], dec)
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{CELL_H}" rx="4" fill="{fill}"/>')
    parts.append(text(x + w / 2, y + 26, f"{counts['pass']}/{dec}", 14, ink, "600"))
    parts.append(text(x + w / 2, y + 44, f"{lo * 100:.0f}–{hi * 100:.0f}%", 10, sub))
    return parts


def build():
    panel = load_panel()
    agg = aggregate(panel)
    order = sorted(agg, key=lambda k: -(agg[k]["pass"] / max(1, agg[k]["pass"] + agg[k]["fail"])))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>']

    svg.append(text(28, 44, "Frontier reliability fingerprints — five models, eight failure modes",
                    20, INK, "700", "start"))
    svg.append(text(28, 68, "cell shade = share of decided runs that failed the mode (darker = worse) · "
                            "passes/decided with Wilson 95% CI · panel 2026-07-02/03",
                    13, INK_SECONDARY, "normal", "start"))

    for i, (_, l1, l2) in enumerate(MODES):
        cx = GRID_LEFT + i * COL_PITCH + CELL_W / 2
        svg.append(text(cx, 102, l1, 11, INK_SECONDARY, "600"))
        if l2:
            svg.append(text(cx, 115, l2, 11, INK_SECONDARY, "600"))
    svg.append(text(AGG_LEFT + AGG_W / 2, 102, "all modes", 11, INK, "700"))
    svg.append(text(AGG_LEFT + AGG_W / 2, 115, "(aggregate)", 11, INK_SECONDARY))

    for r, label in enumerate(order):
        y = GRID_TOP + r * ROW_PITCH
        name = label.replace(" (run A)", " · run A").replace(" (run B)", " · run B")
        svg.append(text(LABEL_W + 20, y + 30, name, 13, INK, "600", "end"))
        if label == "mistral-large":
            svg.append(text(LABEL_W + 20, y + 46, "partial (429 wall)", 10, INK_MUTED, "normal", "end"))
        for i, (slice_name, _, _) in enumerate(MODES):
            svg += cell(GRID_LEFT + i * COL_PITCH, y, CELL_W, panel[label].get(slice_name, {"pass": 0, "fail": 0}))
        c = agg[label]
        svg += cell(AGG_LEFT, y, AGG_W, c)

    ly = GRID_TOP + len(order) * ROW_PITCH + 28
    svg.append(text(28, ly + 14, "fail share:", 11, INK_SECONDARY, "600", "start"))
    for j, s in enumerate((0.0, 0.15, 0.30, 0.50, 0.75)):
        x = 106 + j * 64
        svg.append(f'<rect x="{x}" y="{ly}" width="20" height="20" rx="3" fill="{shade(s)}" '
                   f'stroke="{HAIRLINE}" stroke-width="1"/>')
        svg.append(text(x + 26, ly + 15, f"{s * 100:.0f}%", 11, INK_SECONDARY, "normal", "start"))
    svg.append(f'<rect x="{106 + 5 * 64}" y="{ly}" width="20" height="20" rx="3" fill="{GREY_CELL}" '
               f'stroke="{HAIRLINE}" stroke-width="1"/>')
    svg.append(text(106 + 5 * 64 + 26, ly + 15, "low n / partial", 11, INK_SECONDARY, "normal", "start"))

    svg.append(text(W - 28, ly + 15,
                    "github.com/mightbesaad/llm-reliability-evals · reproduce: slices/panel_stats.py · "
                    "corrected 2026-07-15", 11, INK_MUTED, "normal", "end"))

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "fingerprint-grid-2026-07.svg")
    with open(out, "w") as fh:
        fh.write(build())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
