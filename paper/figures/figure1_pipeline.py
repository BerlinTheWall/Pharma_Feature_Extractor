"""Figure 1: the final version of the extraction pipeline.

Writes figure1_pipeline.png (300 dpi) and figure1_pipeline.svg next to this file.
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INK, LINE, SHADE, ACCENT = "#1f2933", "#52606d", "#eef2f7", "#2f6fb0"

# (title, body, height); boxes are drawn from top to bottom
STEPS = [
    ("Product monograph (PDF)", None, 6),
    ("Text extraction", "PyPDF2, page by page, once for each monograph", 9),
    ("1. Section location",
     "PDF bookmark of the section, read up to the next main section.\n"
     "Without a bookmark: search for the heading, skipping the\n"
     "table of contents and the cross-references", 14),
    ("2. Splitting", "Sections longer than about 8,000 characters are split into\n"
                     "pieces of about 6,000 characters (overlap of 300)", 11),
    ("3. LLM call for each piece", "Prompt written for the field, using only the supplied text,\n"
                                   "temperature 0.1", 11),
    ("4. Merging", "Answers of the pieces merged; repeated items and\nplaceholders removed", 11),
    ("Output table", "One row for each monograph, one column for each field", 9),
]
REPEATED = {2, 3, 4, 5}  # indexes of the steps done for each field
GAP, X, W = 5, 15, 70

total = sum(h for _, _, h in STEPS) + GAP * (len(STEPS) - 1) + 6
fig, ax = plt.subplots(figsize=(7.0, total * 0.085))
ax.set_xlim(0, 100)
ax.set_ylim(0, total)
ax.axis("off")

y = total - 1
pos = []
for title, body, h in STEPS:
    pos.append((y - h, h))
    y -= h + GAP

top_rep = pos[min(REPEATED)][0] + pos[min(REPEATED)][1] + 3.5
bot_rep = pos[max(REPEATED)][0] - 2
ax.add_patch(FancyBboxPatch((6, bot_rep), 88, top_rep - bot_rep, boxstyle="round,pad=0.3,rounding_size=2",
                            linewidth=1.0, edgecolor=ACCENT, facecolor=SHADE, linestyle="--"))
ax.text(8, top_rep - 0.8, "Repeated for each field", ha="left", va="top", fontsize=8.5, color=ACCENT, style="italic")

for i, ((title, body, h), (y0, _)) in enumerate(zip(STEPS, pos)):
    ax.add_patch(FancyBboxPatch((X, y0), W, h, boxstyle="round,pad=0.3,rounding_size=1.5",
                                linewidth=1.1, edgecolor=LINE, facecolor="white"))
    if body is None:
        ax.text(50, y0 + h / 2, title, ha="center", va="center", fontsize=9.5, fontweight="bold", color=INK)
    else:
        ax.text(50, y0 + h - 2.2, title, ha="center", va="top", fontsize=9.5, fontweight="bold", color=INK)
        ax.text(50, y0 + h - 6.2, body, ha="center", va="top", fontsize=7.8, color=INK, linespacing=1.3)
    if i < len(STEPS) - 1:
        nxt = pos[i + 1][0] + pos[i + 1][1]
        ax.add_patch(FancyArrowPatch((50, y0), (50, nxt + 0.3), arrowstyle="-|>", mutation_scale=11,
                                     linewidth=1.1, color=LINE))

for ext in ("png", "svg"):
    fig.savefig(os.path.join(HERE, f"figure1_pipeline.{ext}"), dpi=300, bbox_inches="tight")
print("saved")
